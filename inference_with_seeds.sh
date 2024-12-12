#!/bin/bash

seeds=(431075862 911639571 217313841 311840809 101112)

for seed in "${seeds[@]}"; do
  echo "Running with seed: $seed"
  accelerate launch inference.py \
    --width 768 --height 1024 --num_inference_steps 30 \
    --output_dir "result" \
    --unpaired \
    --data_dir ../VITON-HD \
    --seed "$seed" \
    --test_batch_size 1 \
    --guidance_scale 2.0 \
    --pretrained_model_name_or_path "output/checkpoint-after-epoch-99"
done