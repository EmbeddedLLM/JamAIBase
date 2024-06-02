#!/bin/bash

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

# Build the project in /temp
vite build

# Copy the build files to the build directory
rm -rf build
mv temp build

# Reload PM2 app if not in dev mode
if [ $DEV_MODE -eq 0 ]; then
    pm2 reload ecosystem.config.cjs
fi