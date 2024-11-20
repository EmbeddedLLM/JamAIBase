#!/bin/sh

echo "S3_ACCESS_KEY: $S3_ACCESS_KEY_ID"
echo "S3_SECRET_KEY: $S3_SECRET_ACCESS_KEY"
echo "S3_ENDPOINT: $S3_ENDPOINT"
echo "S3_BUCKET_NAME: $S3_BACKUP_BUCKET_NAME"
echo "OWL_DB_DIR: $OWL_DB_DIR"

du -h /data/main.db

# Substitute environment variables in the template
cat << EOF > /etc/litestream.yml
dbs:
  - path: /data/main.db
    replicas:
      - url: s3://${S3_BACKUP_BUCKET_NAME}/main-db/
        endpoint: ${S3_ENDPOINT}
        access-key-id: ${S3_ACCESS_KEY_ID}
        secret-access-key: ${S3_SECRET_ACCESS_KEY}
        skip-verify: true
        retention: 168h

EOF

cat /etc/litestream.yml

# Run the Litestream command
exec litestream replicate
