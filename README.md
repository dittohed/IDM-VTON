Step 1 (basic setup):
```
git clone https://github.com/dittohed/IDM-VTON.git
sudo apt-get install build-essential unzip
mv IDM-VTON/Makefile .
make download
make setup
make clean
```

Step 2 (conda):
```
source miniconda3/bin/activate
conda env create -f IDM-VTON/environment.yaml
conda activate idm
pip install wandb boto3
pip install --force-reinstall -v "huggingface-hub==0.25.0"
conda install anaconda::cudatoolkit
```

Step 3 (other tools):
```
accelerate config  # Set to bf16
# Set W&B and AWS env variables
```

Step 4 (run in parallel):
```
cd IDM-VTON
./train_xl.sh
```

```
cd IDM-VTON
./upload_to_s3.sh s3://<BUCKET>/<PATH>
```