import os
import random
import argparse
import json
import itertools
import wandb
import boto3
import torch
import torch.nn.functional as F
from torchvision import transforms
from PIL import Image
from transformers import CLIPImageProcessor
from accelerate import Accelerator
from accelerate.utils import ProjectConfiguration
from diffusers import AutoencoderKL, DDPMScheduler
from transformers import CLIPTextModel, CLIPTokenizer, CLIPVisionModelWithProjection, CLIPTextModelWithProjection

from src.unet_hacked_tryon import UNet2DConditionModel
from src.unet_hacked_garmnet import UNet2DConditionModel as UNet2DConditionModel_ref
from src.tryon_pipeline import StableDiffusionXLInpaintPipeline as TryonPipeline

from ip_adapter.ip_adapter import Resampler
from diffusers.utils.import_utils import is_xformers_available
from diffusers.utils.testing_utils import enable_full_determinism
from typing import Literal, Tuple,List
import torch.utils.data as data
import math
from tqdm.auto import tqdm
from diffusers.training_utils import compute_snr
import torchvision.transforms.functional as TF



class VitonHDDataset(data.Dataset):
    def __init__(
        self,
        dataroot_path: str,
        phase: Literal["train", "test"],
        order: Literal["paired", "unpaired"] = "paired",
        size: Tuple[int, int] = (512, 384),
    ):
        super(VitonHDDataset, self).__init__()
        self.dataroot = dataroot_path
        self.phase = phase
        self.height = size[0]
        self.width = size[1]
        self.size = size

        self.norm = transforms.Normalize([0.5], [0.5])
        self.toTensor = transforms.ToTensor()

        with open(
            os.path.join(dataroot_path, phase, "vitonhd_" + phase + "_tagged.json"), "r"
        ) as file1:
            data1 = json.load(file1)

        annotation_list = [
            # "colors",
            # "textures",
            "sleeveLength",
            "neckLine",
            "item",
        ]

        self.annotation_pair = {}
        for k, v in data1.items():
            for elem in v:
                annotation_str = ""
                for template in annotation_list:
                    for tag in elem["tag_info"]:
                        if (
                            tag["tag_name"] == template
                            and tag["tag_category"] is not None
                        ):
                            annotation_str += tag["tag_category"]
                            annotation_str += " "
                self.annotation_pair[elem["file_name"]] = annotation_str


        self.order = order

        self.toTensor = transforms.ToTensor()

        im_names = []
        c_names = []
        dataroot_names = []


        if phase == "train":
            filename = os.path.join(dataroot_path, f"{phase}_pairs.txt")
        else:
            filename = os.path.join(dataroot_path, f"{phase}_pairs.txt")

        with open(filename, "r") as f:
            for line in f.readlines():
                if phase == "train":
                    im_name, _ = line.strip().split()
                    c_name = im_name
                else:
                    if order == "paired":
                        im_name, _ = line.strip().split()
                        c_name = im_name
                    else:
                        im_name, c_name = line.strip().split()

                im_names.append(im_name)
                c_names.append(c_name)
                dataroot_names.append(dataroot_path)

        self.im_names = im_names
        self.c_names = c_names
        self.dataroot_names = dataroot_names
        self.flip_transform = transforms.RandomHorizontalFlip(p=1)
        self.clip_processor = CLIPImageProcessor(do_rescale=False)

    def __getitem__(self, index):
        c_name = self.c_names[index]
        im_name = self.im_names[index]
        # subject_txt = self.txt_preprocess['train']("shirt")
        if c_name in self.annotation_pair:
            cloth_annotation = self.annotation_pair[c_name]
        else:
            cloth_annotation = "shirt"
        
        cloth = Image.open(os.path.join(self.dataroot, self.phase, "cloth", c_name))
        cloth = self.toTensor(cloth)

        im_pil_big = Image.open(
            os.path.join(self.dataroot, self.phase, "image", im_name)
        ).resize((self.width,self.height))
        image = self.toTensor(im_pil_big)

        mask = Image.open(os.path.join(self.dataroot, self.phase, "agnostic-mask", im_name.replace('.jpg','_mask.png'))).resize((self.width,self.height))
        mask = self.toTensor(mask)
        mask = mask[:1]
        densepose_name = im_name
        densepose_map = Image.open(
            os.path.join(self.dataroot, self.phase, "image-densepose", densepose_name)
        ).resize((self.width,self.height))
        pose_img = self.toTensor(densepose_map)  # [-1,1]
 


        if self.phase == "train":
            if random.random() > 0.5:
                cloth = self.flip_transform(cloth)
                mask = self.flip_transform(mask)
                image = self.flip_transform(image)
                pose_img = self.flip_transform(pose_img)



            if random.random()>0.5:
                color_jitter = transforms.ColorJitter(brightness=0.15, contrast=0.25, saturation=0.05, hue=0.05)
                fn_idx, b, c, s, h = transforms.ColorJitter.get_params(
                    color_jitter.brightness, 
                    color_jitter.contrast, 
                    color_jitter.saturation,
                    color_jitter.hue
                )

                image = self.apply_color_jitter(fn_idx, b, c, s, h, image)
                cloth = self.apply_color_jitter(fn_idx, b, c, s, h, cloth)
              
            if random.random() > 0.5:
                scale_val = random.uniform(0.8, 1.2)
                image = transforms.functional.affine(
                    image, angle=0, translate=[0, 0], scale=scale_val, shear=0
                )
                mask = transforms.functional.affine(
                    mask, angle=0, translate=[0, 0], scale=scale_val, shear=0
                )
                pose_img = transforms.functional.affine(
                    pose_img, angle=0, translate=[0, 0], scale=scale_val, shear=0
                )



            if random.random() > 0.5:
                shift_valx = random.uniform(-0.2, 0.2)
                shift_valy = random.uniform(-0.2, 0.2)
                image = transforms.functional.affine(
                    image,
                    angle=0,
                    translate=[shift_valx * image.shape[-1], shift_valy * image.shape[-2]],
                    scale=1,
                    shear=0,
                )
                mask = transforms.functional.affine(
                    mask,
                    angle=0,
                    translate=[shift_valx * mask.shape[-1], shift_valy * mask.shape[-2]],
                    scale=1,
                    shear=0,
                )
                pose_img = transforms.functional.affine(
                    pose_img,
                    angle=0,
                    translate=[
                        shift_valx * pose_img.shape[-1],
                        shift_valy * pose_img.shape[-2],
                    ],
                    scale=1,
                    shear=0,
                )


        image = self.norm(image)
        pose_img =  self.norm(pose_img)

        mask = 1-mask

        cloth_trim =  self.clip_processor(images=cloth, return_tensors="pt").pixel_values


        mask[mask < 0.5] = 0
        mask[mask >= 0.5] = 1

        im_mask = image * mask



        result = {}
        result["c_name"] = c_name
        result["image"] = image
        result["cloth"] = cloth_trim
        result["cloth_pure"] = self.norm(cloth)
        result["inpaint_mask"] = 1-mask
        result["im_mask"] = im_mask
        result["caption"] = "model is wearing a " + cloth_annotation
        result["caption_cloth"] = "a photo of " + cloth_annotation
        result["annotation"] = cloth_annotation
        result["pose_img"] = pose_img


        return result

    def __len__(self):
        return len(self.im_names)
    
    @staticmethod
    def apply_color_jitter(fn_idx, b, c, s, h, img):
        """
        Apply color jitter as in 
        https://pytorch.org/vision/main/_modules/torchvision/transforms/transforms.html#ColorJitter.forward.
        """

        for fn_id in fn_idx:
            if fn_id == 0:
                img = TF.adjust_brightness(img, b)
            elif fn_id == 1:
                img = TF.adjust_contrast(img, c)
            elif fn_id == 2:
                img = TF.adjust_saturation(img, s)
            elif fn_id == 3:
                img = TF.adjust_hue(img, h)

        return img
    

def upload_dir_to_s3(s3_client: boto3.client, bucket: str, local_dir: str, s3_dir: str) -> None:
        """
        Args:
            s3_client: 
                Instance of a boto3 client.
            bucket: 
                S3 bucket name.
            local_dir: 
                Path to directory in the local filesystem.
            s3_dir: 
                Path to directory in the S3 bucket.
        """
        for root, _, files in os.walk(local_dir):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, local_dir)
                s3_file_path = os.path.join(s3_dir, relative_path)
                s3_client.upload_file(local_path, bucket, s3_file_path)


def check_nan_inf(accelerator: Accelerator, tensor: torch.Tensor, tensor_name: str) -> bool:
    if torch.isnan(tensor).any():
        accelerator.print(f"Found NaN values in {tensor_name}.")
        return True
    elif torch.isinf(tensor).any():
        accelerator.print(f"Found infinite values in {tensor_name}.")
        return True

    return False


def parse_args():
    parser = argparse.ArgumentParser(description="Simple example of a training script.")
    parser.add_argument("--pretrained_model_name_or_path",type=str,default="diffusers/stable-diffusion-xl-1.0-inpainting-0.1",required=False,help="Path to pretrained model or model identifier from huggingface.co/models.",)
    parser.add_argument("--pretrained_garmentnet_path",type=str,default="stabilityai/stable-diffusion-xl-base-1.0",required=False,help="Path to pretrained model or model identifier from huggingface.co/models.",)
    parser.add_argument("--chkpt_every",type=int,default=10,help=("Save a checkpoint of the training state every X epochs. These checkpoints are only suitable for resuming"" training using `--resume_from_checkpoint`."),)
    parser.add_argument("--inference_every",type=int,default=10,help=("Run inference on test set every X epochs. If 0, no inference is run during training."),)
    parser.add_argument("--first_batch_only", action="store_true", help="Whether to run inference on first batch only.")
    parser.add_argument("--pretrained_ip_adapter_path",type=str,default="ckpt/ip_adapter/ip-adapter-plus_sdxl_vit-h.bin",help="Path to pretrained ip adapter model. If not specified weights are initialized randomly.",)
    parser.add_argument("--image_encoder_path",type=str,default="ckpt/image_encoder",required=False,help="Path to CLIP image encoder",)
    parser.add_argument("--gradient_checkpointing",action="store_true",help="Whether or not to use gradient checkpointing to save memory at the expense of slower backward pass.",)
    parser.add_argument("--width",type=int,default=768,)
    parser.add_argument("--height",type=int,default=1024,)
    parser.add_argument("--output_dir",type=str,default="output",help="The output directory where the model predictions and checkpoints will be written.",)
    parser.add_argument("--snr_gamma",type=float,default=None,help="SNR weighting gamma to be used if rebalancing the loss. Recommended value is 5.0. ""More details here: https://arxiv.org/abs/2303.09556.",)
    parser.add_argument("--num_tokens",type=int,default=16,help=("IP adapter token nums"),)
    parser.add_argument("--learning_rate",type=float,default=1e-5,help="Learning rate to use.",)
    parser.add_argument("--weight_decay", type=float, default=1e-2, help="Weight decay to use.")
    parser.add_argument("--train_batch_size", type=int, default=6, help="Batch size (per device) for the training dataloader.")
    parser.add_argument("--test_batch_size", type=int, default=4, help="Batch size (per device) for the training dataloader.")
    parser.add_argument("--num_workers_train", type=int, default=16)
    parser.add_argument("--num_workers_test", type=int, default=4)
    parser.add_argument("--num_train_epochs", type=int, default=130)
    parser.add_argument("--max_train_steps",type=int,default=None,help="Total number of training steps to perform.  If provided, overrides num_train_epochs.",)
    parser.add_argument("--noise_offset", type=float, default=None, help="noise offset")
    parser.add_argument("--use_8bit_adam", action="store_true", help="Whether or not to use 8-bit Adam from bitsandbytes.")
    parser.add_argument("--enable_xformers_memory_efficient_attention", action="store_true", help="Whether or not to use xformers.")
    parser.add_argument("--mixed_precision",type=str,default=None,choices=["no", "fp16", "bf16"],help=("Whether to use mixed precision. Choose between fp16 and bf16 (bfloat16). Bf16 requires PyTorch >="" 1.10.and an Nvidia Ampere GPU.  Default to the value of accelerate config of the current system or the"" flag passed with the `accelerate.launch` command. Use this argument to override the accelerate config."),)
    parser.add_argument("--guidance_scale",type=float,default=2.0,)
    parser.add_argument("--seed", type=int, default=42,)    
    parser.add_argument("--num_inference_steps",type=int,default=30,)    
    parser.add_argument("--adam_beta1", type=float, default=0.9, help="The beta1 parameter for the Adam optimizer.")
    parser.add_argument("--adam_beta2", type=float, default=0.999, help="The beta2 parameter for the Adam optimizer.")
    parser.add_argument("--adam_weight_decay", type=float, default=1e-2, help="Weight decay to use.")
    parser.add_argument("--adam_epsilon", type=float, default=1e-08, help="Epsilon value for the Adam optimizer")
    parser.add_argument("--local_rank", type=int, default=-1, help="For distributed training: local_rank")
    parser.add_argument("--data_dir", type=str, default="../VITON-HD", help="For distributed training: local_rank")
    parser.add_argument("--debug_mode", action="store_true", help="Whether to turn on full reproducibility and minimize memory requirements (for tests only).")
    parser.add_argument("--resume_from_checkpoint", type=str, default=None, help="Absolute path to an accelerate checkpoint to resume training with.")
    parser.add_argument("--run_name", type=str, default=None, help="Run name for W&B and AWS S3, should be unique to avoid overwriting in S3.")
    parser.add_argument("--upload_to_s3", action="store_true", help="Whether to additionally upload states and checkpoints to S3.")
    parser.add_argument("--state_to_checkpoint", action="store_true", help="Whether to only convert state to checkpoint and terminate.")
    parser.add_argument("--force_epsilon_update", action="store_true", help="Whether to overwrite optimizer's epsilon value(s) with the CLI one after resuming from checkpoint.")
    parser.add_argument("--check_nan_inf", action="store_true", help="Whether to keep checking if particular tensors contain NaN or -inf/inf.")
    
    args = parser.parse_args()
    env_local_rank = int(os.environ.get("LOCAL_RANK", -1))
    if env_local_rank != -1 and env_local_rank != args.local_rank:
        args.local_rank = env_local_rank

    return args





def main():
    args = parse_args()

    if args.debug_mode:
        torch.manual_seed(args.seed)
        random.seed(args.seed)
        enable_full_determinism()

    wandb.login()
    accelerator_project_config = ProjectConfiguration(project_dir=args.output_dir)
    accelerator = Accelerator(
        mixed_precision=args.mixed_precision,
        project_config=accelerator_project_config,
        log_with="wandb",
    )
    assert args.run_name is not None, "Please provide a run name for wandb logging."
    accelerator.init_trackers(
        project_name="IDM-VTON",
        init_kwargs={"wandb": {"name": args.run_name}}
    )
    if args.upload_to_s3:
        s3_client = boto3.client("s3")

    if accelerator.is_main_process:
        if args.output_dir is not None:
            os.makedirs(args.output_dir, exist_ok=True)

    # Load scheduler, tokenizer and models.
    noise_scheduler = DDPMScheduler.from_pretrained(args.pretrained_model_name_or_path, subfolder="scheduler",rescale_betas_zero_snr=True)
    tokenizer = CLIPTokenizer.from_pretrained(args.pretrained_model_name_or_path, subfolder="tokenizer")
    text_encoder = CLIPTextModel.from_pretrained(args.pretrained_model_name_or_path, subfolder="text_encoder")
    tokenizer_2 = CLIPTokenizer.from_pretrained(args.pretrained_model_name_or_path, subfolder="tokenizer_2")
    text_encoder_2 = CLIPTextModelWithProjection.from_pretrained(args.pretrained_model_name_or_path, subfolder="text_encoder_2")
    vae = AutoencoderKL.from_pretrained(args.pretrained_model_name_or_path,subfolder="vae",torch_dtype=torch.float16,)
    unet_encoder = UNet2DConditionModel_ref.from_pretrained(args.pretrained_garmentnet_path, subfolder="unet")
    unet_encoder.config.addition_embed_type = None
    unet_encoder.config["addition_embed_type"] = None
    image_encoder = CLIPVisionModelWithProjection.from_pretrained(args.image_encoder_path)

    #customize unet start
    unet = UNet2DConditionModel.from_pretrained(args.pretrained_model_name_or_path, subfolder="unet",low_cpu_mem_usage=False, device_map=None)
    unet.config.encoder_hid_dim = image_encoder.config.hidden_size
    unet.config.encoder_hid_dim_type = "ip_image_proj"
    unet.config["encoder_hid_dim"] = image_encoder.config.hidden_size
    unet.config["encoder_hid_dim_type"] = "ip_image_proj"


    state_dict = torch.load(args.pretrained_ip_adapter_path, map_location="cpu")
 
 
    adapter_modules = torch.nn.ModuleList(unet.attn_processors.values())
    adapter_modules.load_state_dict(state_dict["ip_adapter"],strict=True)

    #ip-adapter
    image_proj_model = Resampler(
        dim=image_encoder.config.hidden_size,
        depth=4,
        dim_head=64,
        heads=20,
        num_queries=args.num_tokens,
        embedding_dim=image_encoder.config.hidden_size,
        output_dim=unet.config.cross_attention_dim,
        ff_mult=4,
    ).to(accelerator.device, dtype=torch.float32)

    image_proj_model.load_state_dict(state_dict["image_proj"], strict=True)
    image_proj_model.requires_grad_(True)

    unet.encoder_hid_proj = image_proj_model

    conv_new = torch.nn.Conv2d(
        in_channels=4+4+1+4,
        out_channels=unet.conv_in.out_channels,
        kernel_size=3,
        padding=1,
    )
    torch.nn.init.kaiming_normal_(conv_new.weight)  
    conv_new.weight.data = conv_new.weight.data * 0.  

    conv_new.weight.data[:, :9] = unet.conv_in.weight.data  
    conv_new.bias.data = unet.conv_in.bias.data  

    unet.conv_in = conv_new  # replace conv layer in unet
    unet.config['in_channels'] = 13  # update config
    unet.config.in_channels = 13  # update config
    #customize unet end


    weight_dtype = torch.float32
    if accelerator.mixed_precision == "fp16":
        weight_dtype = torch.float16
    elif accelerator.mixed_precision == "bf16":
        weight_dtype = torch.bfloat16
    vae.to(accelerator.device, dtype=weight_dtype) 
    text_encoder.to(accelerator.device, dtype=weight_dtype)
    text_encoder_2.to(accelerator.device, dtype=weight_dtype)
    image_encoder.to(accelerator.device, dtype=weight_dtype)
    unet_encoder.to(accelerator.device, dtype=weight_dtype)


    vae.requires_grad_(False)
    text_encoder.requires_grad_(False)
    text_encoder_2.requires_grad_(False)
    image_encoder.requires_grad_(False)
    unet_encoder.requires_grad_(False)
    unet.requires_grad_(True)
    if args.debug_mode:
        # Minimize memory requirements but keep one part trainable
        unet.requires_grad_(False)
        image_proj_model.proj_in.requires_grad_(True)



    if args.enable_xformers_memory_efficient_attention:
        if is_xformers_available():
            import xformers

            unet.enable_xformers_memory_efficient_attention()
        else:
            raise ValueError("xformers is not available. Make sure it is installed correctly")
    
    if args.gradient_checkpointing:
        unet.enable_gradient_checkpointing()
        unet_encoder.enable_gradient_checkpointing()
    unet.train()

    if args.use_8bit_adam:
        try:
            import bitsandbytes as bnb
        except ImportError:
            raise ImportError(
                "To use 8-bit Adam, please install the bitsandbytes library: `pip install bitsandbytes`."
            )

        optimizer_class = bnb.optim.AdamW8bit
    else:
        optimizer_class = torch.optim.AdamW

    params_to_opt = itertools.chain(unet.parameters())


    optimizer = optimizer_class(
        params_to_opt,
        lr=args.learning_rate,
        betas=(args.adam_beta1, args.adam_beta2),
        weight_decay=args.adam_weight_decay,
        eps=args.adam_epsilon,
    )
    
    train_dataset = VitonHDDataset(
        dataroot_path=args.data_dir,
        phase="train",
        order="paired",
        size=(args.height, args.width),
    )
    train_dataloader = torch.utils.data.DataLoader(
        train_dataset,
        pin_memory=True,
        shuffle=True,
        batch_size=args.train_batch_size,
        num_workers=args.num_workers_train,
    )
    test_dataset = VitonHDDataset(
        dataroot_path=args.data_dir,
        phase="test",
        order="paired",
        size=(args.height, args.width),
    )
    test_dataloader = torch.utils.data.DataLoader(
        test_dataset,
        shuffle=False,
        batch_size=args.test_batch_size,
        num_workers=args.num_workers_test,
    )

    overrode_max_train_steps = False
    num_update_steps_per_epoch = len(train_dataloader)
    if args.max_train_steps is None:
        args.max_train_steps = args.num_train_epochs * num_update_steps_per_epoch
        overrode_max_train_steps = True


    unet,image_proj_model,unet_encoder,image_encoder,optimizer,train_dataloader = accelerator.prepare(unet, image_proj_model,unet_encoder,image_encoder,optimizer,train_dataloader)

    # We need to recalculate our total training steps as the size of the training dataloader may have changed.
    num_update_steps_per_epoch = len(train_dataloader)
    if overrode_max_train_steps:
        args.max_train_steps = args.num_train_epochs * num_update_steps_per_epoch
    # Afterwards we recalculate our number of training epochs
    args.num_train_epochs = math.ceil(args.max_train_steps / num_update_steps_per_epoch)

    # Train!
    global_step = 0
    first_epoch = 0

    if args.resume_from_checkpoint:
        accelerator.load_state(args.resume_from_checkpoint)
        first_epoch = int(os.path.basename(args.resume_from_checkpoint).split("-")[-1]) + 1
        global_step = first_epoch * num_update_steps_per_epoch
        accelerator.print(f"--- Resuming training from epoch {first_epoch} and global step {global_step} ---")

        if args.force_epsilon_update:
            for param_group in optimizer.param_groups:
                param_group['eps'] = args.adam_epsilon

    progress_bar = tqdm(
        range(0, args.max_train_steps),
        initial=global_step,
        desc="Steps",
        # Only show the progress bar once on each machine.
        disable=not accelerator.is_local_main_process,
    )

    for epoch in range(first_epoch, args.num_train_epochs):
        if args.state_to_checkpoint:  # Ugly workaround to just retrieve checkpoint from state
            epoch -= 1
            break

        for step, batch in enumerate(train_dataloader):
            nan_inf_occured = False

            if args.check_nan_inf:
                for key in batch.keys():
                    if isinstance(batch[key], torch.Tensor):
                        if check_nan_inf(accelerator, batch[key], f"model input ({key})"):
                            nan_inf_occured = True
            
            pixel_values = batch["image"].to(dtype=vae.dtype)
            model_input = vae.encode(pixel_values).latent_dist.sample()
            model_input = model_input * vae.config.scaling_factor

            masked_latents = vae.encode(
                batch["im_mask"].reshape(batch["image"].shape).to(dtype=vae.dtype)
            ).latent_dist.sample()
            masked_latents = masked_latents * vae.config.scaling_factor
            masks = batch["inpaint_mask"]
            # resize the mask to latents shape as we concatenate the mask to the latents
            mask = torch.stack(
                [
                    torch.nn.functional.interpolate(masks, size=(args.height // 8, args.width // 8))
                ]
            )
            mask = mask.reshape(-1, 1, args.height // 8, args.width // 8)

            pose_map = vae.encode(batch["pose_img"].to(dtype=vae.dtype)).latent_dist.sample()
            pose_map = pose_map * vae.config.scaling_factor

            # Sample noise that we'll add to the latents
            noise = torch.randn_like(model_input)

            bsz = model_input.shape[0]
            timesteps = torch.randint(
                    0, noise_scheduler.config.num_train_timesteps, (bsz,), device=model_input.device
                )
            # Add noise to the latents according to the noise magnitude at each timestep
            noisy_latents = noise_scheduler.add_noise(model_input, noise, timesteps)
            latent_model_input = torch.cat([noisy_latents, mask,masked_latents,pose_map], dim=1)
        
        
            text_input_ids = tokenizer(
                batch['caption'],
                max_length=tokenizer.model_max_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt"
            ).input_ids
            text_input_ids_2 = tokenizer_2(
                batch['caption'],
                max_length=tokenizer_2.model_max_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt"
            ).input_ids

            encoder_output = text_encoder(text_input_ids.to(accelerator.device), output_hidden_states=True)
            text_embeds = encoder_output.hidden_states[-2]
            encoder_output_2 = text_encoder_2(text_input_ids_2.to(accelerator.device), output_hidden_states=True)
            pooled_text_embeds = encoder_output_2[0]
            text_embeds_2 = encoder_output_2.hidden_states[-2]
            encoder_hidden_states = torch.concat([text_embeds, text_embeds_2], dim=-1) # concat


            def compute_time_ids(original_size, crops_coords_top_left = (0,0)):
                # Adapted from pipeline.StableDiffusionXLPipeline._get_add_time_ids
                target_size = (args.height, args.height) 
                add_time_ids = list(original_size + crops_coords_top_left + target_size)
                add_time_ids = torch.tensor([add_time_ids])
                add_time_ids = add_time_ids.to(accelerator.device)
                return add_time_ids
            
            add_time_ids = torch.cat(
                [compute_time_ids((args.height, args.height)) for i in range(bsz)]
            )
                    
            img_emb_list = []
            for i in range(bsz):
                img_emb_list.append(batch['cloth'][i])
            
            image_embeds = torch.cat(img_emb_list,dim=0)
            image_embeds = image_encoder(image_embeds, output_hidden_states=True).hidden_states[-2]
            ip_tokens =image_proj_model(image_embeds)
        


            # add cond
            unet_added_cond_kwargs = {"text_embeds": pooled_text_embeds, "time_ids": add_time_ids}
            unet_added_cond_kwargs["image_embeds"] = ip_tokens

            cloth_values = batch["cloth_pure"].to(accelerator.device,dtype=vae.dtype)
            cloth_values = vae.encode(cloth_values).latent_dist.sample()
            cloth_values = cloth_values * vae.config.scaling_factor


            text_input_ids = tokenizer(
                batch['caption_cloth'],
                max_length=tokenizer.model_max_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt"
            ).input_ids
            text_input_ids_2 = tokenizer_2(
                batch['caption_cloth'],
                max_length=tokenizer_2.model_max_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt"
            ).input_ids

        
            encoder_output = text_encoder(text_input_ids.to(accelerator.device), output_hidden_states=True)
            text_embeds_cloth = encoder_output.hidden_states[-2]
            encoder_output_2 = text_encoder_2(text_input_ids_2.to(accelerator.device), output_hidden_states=True)
            text_embeds_2_cloth = encoder_output_2.hidden_states[-2]
            text_embeds_cloth = torch.concat([text_embeds_cloth, text_embeds_2_cloth], dim=-1) # concat


            down,reference_features = unet_encoder(cloth_values,timesteps, text_embeds_cloth,return_dict=False)
            reference_features = list(reference_features)

            noise_pred = unet(latent_model_input, timesteps, encoder_hidden_states,added_cond_kwargs=unet_added_cond_kwargs,garment_features=reference_features).sample
            if args.check_nan_inf:
                if check_nan_inf(accelerator, noise_pred, "model output"):
                    nan_inf_occured = True

            if noise_scheduler.config.prediction_type == "epsilon":
                target = noise
            elif noise_scheduler.config.prediction_type == "v_prediction":
                target = noise_scheduler.get_velocity(model_input, noise, timesteps)
            elif noise_scheduler.config.prediction_type == "sample":
                # We set the target to latents here, but the model_pred will return the noise sample prediction.
                target = model_input
                # We will have to subtract the noise residual from the prediction to get the target sample.
                model_pred = model_pred - noise
            else:
                raise ValueError(f"Unknown prediction type {noise_scheduler.config.prediction_type}")

            
            if args.snr_gamma is None:
                loss = F.mse_loss(noise_pred.float(), target.float(), reduction="mean")
            else:
                # Compute loss-weights as per Section 3.4 of https://arxiv.org/abs/2303.09556.
                # Since we predict the noise instead of x_0, the original formulation is slightly changed.
                # This is discussed in Section 4.2 of the same paper.
                snr = compute_snr(noise_scheduler, timesteps)
                if noise_scheduler.config.prediction_type == "v_prediction":
                    # Velocity objective requires that we add one to SNR values before we divide by them.
                    snr = snr + 1
                mse_loss_weights = (
                    torch.stack([snr, args.snr_gamma * torch.ones_like(timesteps)], dim=1).min(dim=1)[0] / snr
                )

                loss = F.mse_loss(noise_pred.float(), target.float(), reduction="none")
                loss = loss.mean(dim=list(range(1, len(loss.shape)))) * mse_loss_weights
                loss = loss.mean()

            if args.check_nan_inf:
                if check_nan_inf(accelerator, loss, "loss"):
                    nan_inf_occured = True

            # Compute average loss across processes, 
            # otherwise only the main process' loss will be logged
            loss_log = accelerator.gather(loss.repeat(args.train_batch_size)).mean().item()

            # Backpropagate
            accelerator.backward(loss)

            if accelerator.sync_gradients:
                accelerator.clip_grad_norm_(params_to_opt, 1.0)

            optimizer.step()
            optimizer.zero_grad()

            if args.check_nan_inf:
                for name, param in unet.named_parameters():
                    if check_nan_inf(accelerator, param, f"model params ({name})"):
                        nan_inf_occured = True

            progress_bar.update(1)
            global_step += 1
            accelerator.log({"loss": loss_log}, step=global_step)
            progress_bar.set_postfix({"loss": loss_log})

            if global_step >= args.max_train_steps:
                break

            if nan_inf_occured:
                save_path = os.path.join(args.output_dir, "state-after-instability")
                if not os.path.isdir(save_path):
                    accelerator.print(f"--- Saving training state to {save_path} ---")
                    accelerator.save_state(save_path)
        # Evaluate
        is_last_epoch = (epoch+1 == args.num_train_epochs)
        if args.inference_every != 0 and ((epoch+1) % args.inference_every == 0 or is_last_epoch):
            accelerator.print(f"--- Running inference at epoch {epoch} ---")
            if accelerator.is_main_process:
                with torch.no_grad():
                    with torch.cuda.amp.autocast():
                        unwrapped_unet= accelerator.unwrap_model(unet)
                        newpipe = TryonPipeline.from_pretrained(
                            args.pretrained_model_name_or_path,
                            unet=unwrapped_unet,
                            vae= vae,
                            scheduler=noise_scheduler,
                            tokenizer=tokenizer,
                            tokenizer_2=tokenizer_2,
                            text_encoder=text_encoder,
                            text_encoder_2=text_encoder_2,
                            image_encoder=image_encoder,
                            unet_encoder = unet_encoder,
                            torch_dtype=torch.float16,
                            add_watermarker=False,
                            safety_checker=None,
                        ).to(accelerator.device)
                        with torch.no_grad():
                            for sample in test_dataloader:
                                img_emb_list = []
                                for i in range(sample['cloth'].shape[0]):
                                    img_emb_list.append(sample['cloth'][i])

                                prompt = sample["caption"]

                                num_prompts = sample['cloth'].shape[0]                                        
                                negative_prompt = "monochrome, lowres, bad anatomy, worst quality, low quality"

                                if not isinstance(prompt, List):
                                    prompt = [prompt] * num_prompts
                                if not isinstance(negative_prompt, List):
                                    negative_prompt = [negative_prompt] * num_prompts

                                image_embeds = torch.cat(img_emb_list,dim=0)


                                with torch.inference_mode():
                                    (
                                        prompt_embeds,
                                        negative_prompt_embeds,
                                        pooled_prompt_embeds,
                                        negative_pooled_prompt_embeds,
                                    ) = newpipe.encode_prompt(
                                        prompt,
                                        num_images_per_prompt=1,
                                        do_classifier_free_guidance=True,
                                        negative_prompt=negative_prompt,
                                    )
                                
                                
                                    prompt = sample["caption_cloth"]
                                    negative_prompt = "monochrome, lowres, bad anatomy, worst quality, low quality"

                                    if not isinstance(prompt, List):
                                        prompt = [prompt] * num_prompts
                                    if not isinstance(negative_prompt, List):
                                        negative_prompt = [negative_prompt] * num_prompts


                                    with torch.inference_mode():
                                        (
                                            prompt_embeds_c,
                                            _,
                                            _,
                                            _,
                                        ) = newpipe.encode_prompt(
                                            prompt,
                                            num_images_per_prompt=1,
                                            do_classifier_free_guidance=False,
                                            negative_prompt=negative_prompt,
                                        )
                                    


                                    generator = torch.Generator(newpipe.device).manual_seed(args.seed) if args.seed is not None else None
                                    images = newpipe(
                                        prompt_embeds=prompt_embeds,
                                        negative_prompt_embeds=negative_prompt_embeds,
                                        pooled_prompt_embeds=pooled_prompt_embeds,
                                        negative_pooled_prompt_embeds=negative_pooled_prompt_embeds,
                                        num_inference_steps=args.num_inference_steps,
                                        generator=generator,
                                        strength = 1.0,
                                        pose_img = sample['pose_img'],
                                        text_embeds_cloth=prompt_embeds_c,
                                        cloth = sample["cloth_pure"].to(accelerator.device),
                                        mask_image=sample['inpaint_mask'],
                                        image=(sample['image']+1.0)/2.0, 
                                        height=args.height,
                                        width=args.width,
                                        guidance_scale=args.guidance_scale,
                                        ip_adapter_image = image_embeds,
                                    )[0]

                                wandb_images = [wandb.Image(image) for image in images]
                                accelerator.get_tracker("wandb").log(
                                    {"Results": wandb_images}, step=global_step
                                )
                                if args.first_batch_only:
                                    break

                del unwrapped_unet
                del newpipe                
                torch.cuda.empty_cache()

        # Store accelerator for resuming training (if needed)
        if (epoch+1) % args.chkpt_every == 0:
            dir_name = f"state-after-epoch-{epoch}"
            save_path = os.path.join(args.output_dir, dir_name)
            accelerator.print(f"--- Saving training state to {save_path} ---")
            accelerator.save_state(save_path)
            if args.upload_to_s3:
                upload_dir_to_s3(s3_client, "tpx-vton", save_path, f"{args.run_name}/{dir_name}")
            
    # Save the final model, to be used in inference.py
    accelerator.wait_for_everyone()
    if accelerator.is_main_process:
        unwrapped_unet = accelerator.unwrap_model(
            unet, keep_fp32_wrapper=True
        )
        pipeline = TryonPipeline.from_pretrained(
            args.pretrained_model_name_or_path,
            unet=unwrapped_unet,
            vae=vae,
            scheduler=noise_scheduler,
            tokenizer=tokenizer,
            tokenizer_2=tokenizer_2,
            text_encoder=text_encoder,
            text_encoder_2=text_encoder_2,
            image_encoder=image_encoder,
            unet_encoder=unet_encoder,
            torch_dtype=torch.float16,
            add_watermarker=False,
            safety_checker=None,
        )
        dir_name = f"checkpoint-after-epoch-{epoch}"
        save_path = os.path.join(args.output_dir, dir_name)
        accelerator.print(f"--- Saving final checkpoint to {save_path} ---")
        pipeline.save_pretrained(save_path)
        if args.upload_to_s3:
            upload_dir_to_s3(s3_client, "tpx-vton", save_path, f"{args.run_name}/{dir_name}")

    accelerator.end_training()

                
if __name__ == "__main__":
    main()    
