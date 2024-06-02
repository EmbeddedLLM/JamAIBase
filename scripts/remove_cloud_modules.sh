#!/usr/bin/env bash

find . -type f -name "cloud*.py" -delete
find . -type f -name "compose.*.cloud.yml" -delete
find . -type d -name "(cloud)" -exec rm -rf {} +
rm -f services/app/ecosystem.config.cjs
rm -f services/app/ecosystem.json
