Get-ChildItem -Recurse -File -Filter "cloud_*.py" | Remove-Item -Force
Get-ChildItem -Recurse -File -Filter "cloud_*.json" | Remove-Item -Force
Get-ChildItem -Recurse -File -Filter "*_cloud.json" | Remove-Item -Force
Get-ChildItem -Recurse -File -Filter "compose.*.cloud.yml" | Remove-Item -Force
Get-ChildItem -Recurse -Directory -Filter "(cloud)" | Remove-Item -Recurse -Force
if (Test-Path -Path "docker\enterprise") {
    Remove-Item -Path "docker\enterprise" -Recurse -Force
}

# Remove a file or folder quietly
# Like linux "rm -rf"
function quiet_rm($item)
{
  if (Test-Path $item) {
    echo "Removing $item"
    Remove-Item -Force $item
  }
}
quiet_rm "services/app/ecosystem.config.cjs"
quiet_rm "services/appecosystem.json"
quiet_rm ".github/workflows/trigger-push-gh-image.yml"
quiet_rm ".github/workflows/ci.cloud.yml"