"""
Create a grid of images from the outputs of 2 methods run for the same input images (with 
multiple seeds).

Expected folder structure inside folder pointed by `FOLDERS_PATH`:
├── <method1>
    ├── <input1>
│   │   ├── <output_for_seed1>
│   │   ├── ...
│   │   └── <output_for_seedN>
│   └── ...
└   └── <inputN>
│   │   ├── <output_for_seed1>
│   │   ├── ...
│   │   └── <output_for_seedN>
└── <method2>
    ...
"""

from pathlib import Path
from tqdm import tqdm
from PIL import Image


if __name__ == "__main__":
    FOLDERS_PATH = Path("../tmp")
    OUT_FOLDER = Path("local/comparison_results")

    N_IMAGES = 5  # Number of images per input (number of seeds)
    WIDTH = 768
    HEIGHT = 1024

    OUT_FOLDER.mkdir(exist_ok=True)
    method_folders = list(FOLDERS_PATH.glob("*"))
    vton_inputs = [folder.stem for folder in method_folders[0].glob("*")]

    for vton_input in tqdm(vton_inputs):
        grid_image = Image.new("RGB", (N_IMAGES*WIDTH, 2*HEIGHT), (255, 255, 255))

        images_up = list((method_folders[0]/vton_input).glob("*"))
        images_down = list((method_folders[1]/vton_input).glob("*"))

        for i in range(N_IMAGES):
            image_up = Image.open(images_up[i])
            image_down = Image.open(images_down[i])

            grid_image.paste(image_up, (i*WIDTH, 0))
            grid_image.paste(image_down, (i*WIDTH, HEIGHT))

        grid_image.save(OUT_FOLDER/f"{vton_input}.png")