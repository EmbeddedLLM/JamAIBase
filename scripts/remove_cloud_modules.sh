#!/usr/bin/env bash

rm -rf docker/enterprise/
find . -type f -name "cloud_*.py" -delete
find . -type f -name "cloud_*.json" -delete
find . -type f -name "*_cloud.json" -delete
find . -type f -name "compose.*.cloud.yml" -delete
find . -type d -name "(cloud)" -exec rm -rf {} +
rm -f services/app/ecosystem.config.cjs
rm -f services/app/ecosystem.json
rm -f .github/workflows/trigger-push-gh-image.yml
rm -f .github/workflows/ci.cloud.yml
