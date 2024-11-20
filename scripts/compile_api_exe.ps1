.\scripts\remove_cloud_modules.ps1
cd .\clients\python
pip install .
cd .\..\..\services\api
pip install -e .
pip install pyinstaller==6.9.0
pyinstaller api.spec