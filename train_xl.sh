CUDA_VISIBLE_DEVICES=0,1,2,3 accelerate launch train_xl.py \
    --gradient_checkpointing \
    --use_8bit_adam \
    --inference_every 5 \
    --run_name 2024-12-06 \
    --upload_to_s3