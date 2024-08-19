.\scripts\remove_cloud_modules.ps1
cd .\clients\python
pip install .
cd .\..\..\services\docio
pip install -e .
pip install pyinstaller==6.9.0
pip install cryptography==42.0.8
pip install python-magic-bin
pyinstaller docio.spec