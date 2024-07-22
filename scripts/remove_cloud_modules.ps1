Get-ChildItem -Recurse -File -Filter "cloud*.py" | Remove-Item -Force
Get-ChildItem -Recurse -File -Filter "cloud*.json" | Remove-Item -Force
Get-ChildItem -Recurse -File -Filter "compose.*.cloud.yml" | Remove-Item -Force
Get-ChildItem -Recurse -Directory -Filter "(cloud)" | Remove-Item -Recurse -Force
Remove-Item -Force "services/app/ecosystem.config.cjs"
Remove-Item -Force "services/app/ecosystem.json"