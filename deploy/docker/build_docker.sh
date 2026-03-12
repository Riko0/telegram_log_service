#!/bin/bash

IMAGE_NAME="telegram-log-service"
IMAGE_TAG="latest"

echo "Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG}..."
sudo docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" -f deploy/docker/Dockerfile .

if [ $? -eq 0 ]; then
    echo "Docker image built successfully: ${IMAGE_NAME}:${IMAGE_TAG}"
    echo "Attempting to run the Docker container..."

    sudo docker run --rm -it \
        -p 5000:5000 \
        --env-file .env \
        "${IMAGE_NAME}:${IMAGE_TAG}"

    if [ $? -eq 0 ]; then
        echo "Docker container started successfully."
    else
        echo "Error: Docker container failed to start."
    fi
else
    echo "Error: Docker image build failed. Cannot run container."
fi
