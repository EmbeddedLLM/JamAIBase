#!/bin/bash
echo ""
echo ""
curl -i -X POST http://localhost:8001/config \
  --form config=@kong_external.yml

echo ""
curl -i -X POST http://localhost:8011/config \
  --form config=@kong_internal.yml
echo ""