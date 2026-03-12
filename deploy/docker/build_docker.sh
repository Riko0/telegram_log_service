#!/bin/bash

# Define the image name and tag
IMAGE_NAME="telegram-log-service"
IMAGE_TAG="latest"

# Build the Docker image
# The -t flag tags the image with a name and optional tag (e.g., my-python-app:latest)
# The . at the end specifies the build context (current directory)
echo "Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG}..."
sudo docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" -f deploy/docker/Dockerfile .

# Check if the build was successful
if [ $? -eq 0 ]; then
    echo "Docker image built successfully: ${IMAGE_NAME}:${IMAGE_TAG}"
    echo "Attempting to run the Docker container..."

    # Run the Docker container
    # -d runs the container in detached mode (in the background)
    # -p maps a port from the host to the container (e.g., host_port:container_port)
    # If your application listens on a specific port (e.g., 8080 as exposed in the Dockerfile),
    # you might want to uncomment and adjust the -p flag.
    # For a simple script that just runs and exits, -it might be more appropriate.
    # docker run -it "${IMAGE_NAME}:${IMAGE_TAG}"
    sudo docker run --rm -it -p 5000:5000 -v .:/app "${IMAGE_NAME}:${IMAGE_TAG}"

    # The --rm flag automatically removes the container when it exits.
    # The -it flags provide an interactive terminal.
    # If your application is a long-running service (like a web server), you might prefer -d (detached mode)
    # and potentially -p for port mapping.

    if [ $? -eq 0 ]; then
        echo "Docker container started successfully."
    else
        echo "Error: Docker container failed to start."
    fi
else
    echo "Error: Docker image build failed. Cannot run container."
fi
