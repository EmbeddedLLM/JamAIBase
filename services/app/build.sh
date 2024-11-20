#!/bin/bash

set -e
source .env
# Set the flag variable
DEV_MODE=1

# Check if --dev flag is provided
while [[ $# -gt 0 ]]; do
    case $1 in
        --reload)
            DEV_MODE=0
            shift
            ;;
        *)
            echo "Invalid argument: $1"
            exit 1
            ;;
    esac
done

if [ -f "src/routes/_layout.server.ts" ]; then
    mv "src/routes/_layout.server.ts" "src/routes/+layout.server.ts"
fi
if [ -f "src/routes/+layout.ts" ]; then
    mv "src/routes/+layout.ts" "src/routes/_layout.ts"
fi

# SPA hack
if [ "$PUBLIC_IS_SPA" == "true" ]; then
    mv "src/routes/+layout.server.ts" "src/routes/_layout.server.ts"
    mv "src/routes/_layout.ts" "src/routes/+layout.ts"
fi

# Build the project in /temp
vite build

# Copy the build files to the build directory
rm -rf build
mv temp build

if [ "$PUBLIC_IS_SPA" == "true" ]; then
    mv "src/routes/_layout.server.ts" "src/routes/+layout.server.ts"
    mv "src/routes/+layout.ts" "src/routes/_layout.ts"
fi

# Reload PM2 app if not in dev mode
if [ $DEV_MODE -eq 0 ]; then
    pm2 reload ecosystem.config.cjs
fi