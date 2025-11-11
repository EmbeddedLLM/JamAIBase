#!/usr/bin/env bash

set -e

# Get the current date in YYYYMMDD format
current_date=$(date +"%Y%m%d")

docker build -t ghcr.io/embeddedllm/jamaibase/owl.base:latest -f docker/Dockerfile.owl.base .
docker image tag ghcr.io/embeddedllm/jamaibase/owl.base:latest ghcr.io/embeddedllm/jamaibase/owl.base:${current_date}
docker push ghcr.io/embeddedllm/jamaibase/owl.base:latest
docker push ghcr.io/embeddedllm/jamaibase/owl.base:${current_date}
