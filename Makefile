download:
	wget https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus_sdxl_vit-h.bin?download=true
	wget https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors?download=true
	curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"

setup:
	unzip awscliv2.zip
	sudo ./aws/install
	aws s3 cp ${DATASET_S3_URI} ./
	unzip -qq VITON-HD.zip

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

clean:
	rm VITON-HD.zip
	rm awscliv2.zip