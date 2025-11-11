#!/usr/bin/env bash

rm -rf k8s/
rm -rf docker/enterprise/
find . -type f -iname "*cloud*.md" -delete
find . -type f -iname "*cloud*.py" -delete
find . -type f -iname "cloud_*.json" -delete
find . -type f -iname "*_cloud.json" -delete
find . -type f -iname "compose.*.cloud.yml" -delete
find . -type d -iname "*cloud" -exec rm -rf {} +
find . -type d -iname "(cloud)" -exec rm -rf {} +
rm -f services/app/ecosystem.config.cjs
rm -f services/app/ecosystem.json
rm -f .github/workflows/trigger-push-gh-image.yml
rm -f .github/workflows/ci.cloud.yml
