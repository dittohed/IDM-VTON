download:
	wget https://www.dropbox.com/scl/fi/xu08cx3fxmiwpg32yotd7/zalando-hd-resized.zip?rlkey=ks83mdv2pvmrdl2oo2bmmn69w&e=1&st=cw2jav9b&dl=0
	wget https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus_sdxl_vit-h.bin?download=true
	wget https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors?download=true
	curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"

setup:
	unzip -qq 'zalando-hd-resized.zip?rlkey=ks83mdv2pvmrdl2oo2bmmn69w' -d VITON-HD
	unzip awscliv2.zip

	cp IDM-VTON/vitonhd_train_tagged.json VITON-HD/train/
	cp IDM-VTON/vitonhd_test_tagged.json VITON-HD/test/
	cp IDM-VTON/vitonhd_test_pairs.txt VITON-HD/test_pairs.txt
	
	mv 'ip-adapter-plus_sdxl_vit-h.bin?download=true' ip-adapter-plus_sdxl_vit-h.bin
	mkdir IDM-VTON/ckpt/ip_adapter
	mv ip-adapter-plus_sdxl_vit-h.bin IDM-VTON/ckpt/ip_adapter/

	mv 'model.safetensors?download=true' model.safetensors
	mv model.safetensors IDM-VTON/ckpt/image_encoder/

	chmod +x IDM-VTON/train_xl.sh
	chmod +x IDM-VTON/upload_to_s3.sh

	sudo ./aws/install

clean:
	rm 'zalando-hd-resized.zip?rlkey=ks83mdv2pvmrdl2oo2bmmn69w'
	rm awscliv2.zip