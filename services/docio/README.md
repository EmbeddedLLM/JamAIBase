# Document IO (DocIO)

This is a package and a service that helps to parse file. Currently it support parsing of

- txt
- md
- pdf

## Compile Windows Executable File

1. Create python virtual environment.
2. `cd services\docio`.
3. Install the python dependencies in the python virtual environment. PowerShell: `.\scripts\SetupWinExeEnv.ps1`.
4. Generate Python executable file. PowerShell: `.\scripts\GenerateWinExe.ps1`. The generate output can be found in `dist`.
