download:
	wget https://www.dropbox.com/scl/fi/xu08cx3fxmiwpg32yotd7/zalando-hd-resized.zip?rlkey=ks83mdv2pvmrdl2oo2bmmn69w&e=1&st=cw2jav9b&dl=0
	curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

setup:
	unzip -qq 'zalando-hd-resized.zip?rlkey=ks83mdv2pvmrdl2oo2bmmn69w' -d VITON-HD

	cp IDM-VTON/vitonhd_train_tagged.json VITON-HD/train/
	cp IDM-VTON/vitonhd_test_tagged.json VITON-HD/test/
	cp IDM-VTON/vitonhd_test_pairs.txt VITON-HD/test_pairs.txt
	
	chmod +x Miniconda3-latest-Linux-x86_64.sh
	bash Miniconda3-latest-Linux-x86_64.sh -b -p miniconda3
	source miniconda3/bin/activate
	conda env create -f IDM-VTON/environment.yaml
	conda activate idm
	pip install wandb boto3

clean:
	rm 'zalando-hd-resized.zip?rlkey=ks83mdv2pvmrdl2oo2bmmn69w'
	rm Miniconda3-latest-Linux-x86_64.sh