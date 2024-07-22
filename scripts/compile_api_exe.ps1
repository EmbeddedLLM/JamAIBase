.\scripts\remove_cloud_modules.ps1
cd .\clients\python
pip install .
cd .\..\..\services\api
pip install -e .
pip install pyinstaller
pyinstaller api.spec