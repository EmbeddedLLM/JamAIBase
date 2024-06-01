#!/usr/bin/env bash

set -e

find . -type f -name "cloud*.py" -delete
find . -type f -name "compose.*.cloud.yml" -delete
find . -type d -name "(cloud)" -exec rm -rf {} +
rm services/app/ecosystem.config.cjs
rm services/app/ecosystem.json
