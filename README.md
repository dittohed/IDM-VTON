Step 1 (basic setup):
```
git clone https://github.com/dittohed/IDM-VTON.git
sudo apt-get install build-essential unzip
mv IDM-VTON/Makefile .
# Set AWS env variables
export DATASET_S3_URI=s3://<BUCKET>/<PATH>
make download
make setup
make clean
```

Step 2 (environment):
```
python -m venv idm  # Tested with Python 3.10.12 only
source idm/bin/activate
pip install -r IDM-VTON/requirements.txt
```

Step 3 (other tools):
```
accelerate config  # Set to FP16
```

Step 4 (run in parallel):
```
# Set W&B variable
cd IDM-VTON
./train_xl.sh
```

```
cd IDM-VTON
./upload_to_s3.sh s3://<BUCKET>/<PATH>
```