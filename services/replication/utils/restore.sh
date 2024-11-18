#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | sed 's/#.*//g' | xargs)
else
    echo "Error: .env file not found."
    exit 1
fi
echo "S3_ACCESS_KEY: $S3_ACCESS_KEY_ID"
echo "S3_SECRET_KEY: $S3_SECRET_ACCESS_KEY"
echo "S3_ENDPOINT: $S3_ENDPOINT"
echo "S3_BUCKET_NAME: $S3_BACKUP_BUCKET_NAME"

# Define variables
OUTPUT_DB="db/main.db"
SOURCE_DB="/data/main.db"

# Run the litestream restore command with inline configuration
litestream restore -config <(cat << EOF
dbs:
  - path: /data/main.db
    replicas:
      - url: s3://${S3_BACKUP_BUCKET_NAME}/main-db/
        endpoint: ${S3_ENDPOINT}
        access-key-id: ${S3_ACCESS_KEY_ID}
        secret-access-key: ${S3_SECRET_ACCESS_KEY}
        skip-verify: true
EOF
) -o "$OUTPUT_DB" "$SOURCE_DB"

# Check if the command was successful
if [ $? -eq 0 ]; then
    echo "Litestream restore completed successfully."
else
    echo "Error: Litestream restore failed."
    exit 1
fi