.\scripts\remove_cloud_modules.ps1
cd .\clients\python
pip install .
cd .\..\..\services\docio
pip install -e .
pip install pyinstaller
pyinstaller docio.spec