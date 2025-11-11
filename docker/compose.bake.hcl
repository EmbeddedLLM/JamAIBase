group "default" {
  targets = ["owl", "jambu"]
}

target "owl" {
  dockerfile = "docker/Dockerfile.owl"
  cache-from = ["type=azblob,name=owl-cache,account_url=AZURE_STORAGE_ACCOUNT_URL,secret_access_key=AZURE_STORAGE_ACCESS_KEY"]
  cache-to   = ["type=azblob,name=owl-cache,mode=max,account_url=AZURE_STORAGE_ACCOUNT_URL,secret_access_key=AZURE_STORAGE_ACCESS_KEY"]
}

target "jambu" {
  dockerfile = "docker/Dockerfile.frontend"
  cache-from = ["type=azblob,name=jambu-cache,account_url=AZURE_STORAGE_ACCOUNT_URL,secret_access_key=AZURE_STORAGE_ACCESS_KEY"]
  cache-to   = ["type=azblob,name=jambu-cache,mode=max,account_url=AZURE_STORAGE_ACCOUNT_URL,secret_access_key=AZURE_STORAGE_ACCESS_KEY"]
}