CUDA_VISIBLE_DEVICES=0,1,2,3 accelerate launch train_xl.py \
    --gradient_checkpointing \
    --use_8bit_adam