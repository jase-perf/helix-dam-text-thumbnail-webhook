#!/bin/bash

# Stop and remove the existing container if it exists
echo "Stopping existing container if any"
docker stop text-thumbnail-webhook || true
docker rm text-thumbnail-webhook || true

echo "Starting new container"
# Start the new container
docker run -d \
  --name text-thumbnail-webhook \
  --restart unless-stopped \
  -p 8080:8080 \
  -e DAM_URL="http://10.0.0.1" \
  -e ACCOUNT_KEY="your_account_key" \
  text-thumbnail-webhook

echo "Container started"
echo "You can tail logs with this command: docker logs -f text-thumbnail-webhook"