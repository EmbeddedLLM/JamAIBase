# JamAI Base API service

## Compiling Executable

### Windows

1. Create fresh python environment: `conda create -n jamaiapi python=3.10`.
2. Activate the python environment: `conda activate jamaiapi`.
3. Remove any of the cloud modules in PowerShell: `.\scripts\remove_cloud_modules.ps1`.
4. Install JamAI Base Python SDK: `pip install .\clients\python`
5. Install api service: `cd services\api ; pip install -e .`
6. Install Pyinstaller: `pip install pyinstaller`
7. Create Pyinstaller executable: `pyinstaller api.spec`
