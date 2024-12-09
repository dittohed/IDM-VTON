#!/bin/bash

S3_PATH="$1"

while true; do
    aws s3 sync output "$S3_PATH"
    sleep 3h
done