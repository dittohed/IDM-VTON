Step 1 (basic setup):
```
git clone https://github.com/dittohed/IDM-VTON.git
sudo apt-get install build-essential unzip
mv IDM-VTON/Makefile .
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