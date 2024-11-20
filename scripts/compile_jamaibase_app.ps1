.\scripts\remove_cloud_modules.ps1
cd .\services\app
npm i
# Load the content of the .env file into a variable
$content = Get-Content .\.env.example
# Modify the content
$content = $content -replace 'PUBLIC_JAMAI_URL=""', 'PUBLIC_JAMAI_URL="http://localhost:6969"'
$content = $content -replace 'PUBLIC_IS_SPA="false"', 'PUBLIC_IS_SPA="true"'
# Add CHECK_ORIGIN=false to the content
$content += 'CHECK_ORIGIN="false"'
# Write the updated content back to the .env file
$content | Set-Content .\.env
npm run make