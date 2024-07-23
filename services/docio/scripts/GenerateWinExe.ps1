if (Test-Path -Path ".\dist") {
    Remove-Item -Path ".\dist" -Recurse -Force
}

Get-Command python
pyinstaller .\docio.spec
Copy-Item -Path .\.env -Destination .\dist\docio\