import random
from pathlib import Path

import torchvision.transforms.functional as TF

from train_xl import VitonHDDataset


OUT_DIR = Path("sampled_images")
N_SAMPLES = 16


if __name__ == "__main__":
    train_dataset = VitonHDDataset(
        dataroot_path="../VITON-HD",
        phase="train",
        order="paired",
        size=(1024, 768),
    )
    sampled_indices = random.sample(range(len(train_dataset)), N_SAMPLES)
    OUT_DIR.mkdir(exist_ok=True)

    for i, idx in enumerate(sampled_indices):
        data_dict = train_dataset[idx]
        name = Path(data_dict["c_name"]).stem

        # [-1, 1] -> [0, 1]
        image = (data_dict["image"]+1)/2 
        cloth = (data_dict["cloth_pure"]+1)/2

        TF.to_pil_image(image).save(OUT_DIR/f"{name}_image.png")
        TF.to_pil_image(cloth).save(OUT_DIR/f"{name}_cloth.png")
        with open(OUT_DIR/f"{name}_cloth_caption.txt", "w") as f:
            f.write(data_dict["caption_cloth"])