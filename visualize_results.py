"""
Create a grid of images from the results of the experiments, where one column corresponds to 
one directory with outputs across the training steps for a VTON problem.

Each directory is assumed to have the same number of images, including f"Results_{step}*" files
and a reference image without step number.
"""


import re
from pathlib import Path

from PIL import Image


def sort_images_by_step(images):
    def extract_step(filename):
        match = re.search(r"Results_(\d+)_", filename)
        return int(match.group(1)) if match else 0
    
    return sorted(images, key=lambda x: extract_step(x[0]))


if __name__ == "__main__":
    FOLDERS_PATH = Path("local/results")
    WIDTH = 768
    HEIGHT = 1024

    all_images = []
    grid_width = 0
    grid_height = 0

    for folder in FOLDERS_PATH.glob("*"):
        images = [
            (path.stem, Image.open(path).resize((WIDTH, HEIGHT)))
            for path in folder.glob("*")
        ]
        images = sort_images_by_step(images)

        all_images.append(images)
        grid_width += 2*WIDTH  # Reference image and output image side-by-side
        
    grid_height += (len(all_images[0])-1) * HEIGHT  # Reference image doesn't have its row
    grid_image = Image.new("RGB", (grid_width, grid_height), (255, 255, 255))

    x_offset = 0
    for images in all_images:
        y_offset = 0
        _, ref_image = images.pop(0)
        
        for _, image in images:
            grid_image.paste(ref_image, (x_offset, y_offset))
            grid_image.paste(image, (x_offset+WIDTH, y_offset))
            y_offset += HEIGHT

        x_offset += 2*WIDTH

    grid_image.save("output_grid.png")