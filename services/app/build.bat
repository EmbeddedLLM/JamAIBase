@echo off
setlocal enabledelayedexpansion

for /f "usebackq delims=" %%a in (".env") do (
    set "line=%%a"
    if not "!line!"=="" (
        for /f "tokens=1,* delims==" %%b in ("!line!") do (
            set "key=%%b"
            set "value=%%c"
            set "key=!key:"=!"
            set "key=!key: =!"
            if not "!key!"=="" if not "!value!"=="" (
                for /f "tokens=1,* delims=#" %%d in ("!value!") do set "value=%%d"
                set "value=!value:"=!"
                call :trim value
                set "!key!=!value!"
            )
        )
    )
)

rem Fallback
powershell -Command "Get-Content .env | ForEach-Object { $line = $_ -replace '#.*', ''; if ($line.Trim()) { $key, $value = $line.Split('=', 2); $value = $value.Trim().Trim('\"'); [Environment]::SetEnvironmentVariable($key, $value, 'Process') } }"

echo %BASE_URL%
echo %PUBLIC_JAMAI_URL%
echo %OWL_URL%
echo %PUBLIC_IS_SPA%

rem Set the flag variable
set DEV_MODE=1

rem Check if --reload flag is provided
if "%1" == "--reload" (
    set DEV_MODE=0
)

if exist "src\routes\_layout.server.ts" (
    ren "src\routes\_layout.server.ts" "+layout.server.ts"
)
if exist "src\routes\+layout.ts" (
    ren "src\routes\+layout.ts" "_layout.ts"
)

rem SPA hack
if "%PUBLIC_IS_SPA%" == "true" (
    ren "src\routes\+layout.server.ts" "_layout.server.ts"
    ren "src\routes\_layout.ts" "+layout.ts"
)

rem Build the project in /temp
call vite build

rem Copy the build files to the build directory
if exist build rmdir /s /q build
move temp build

if "%PUBLIC_IS_SPA%" == "true" (
    ren "src\routes\_layout.server.ts" "+layout.server.ts"
    ren "src\routes\+layout.ts" "_layout.ts"
)

rem Reload PM2 app if not in dev mode
if %DEV_MODE% equ 0 (
    call pm2 reload ecosystem.config.cjs
)

endlocal
goto :eof

:trim
setlocal enabledelayedexpansion
set "x=!%1!"
for /f "tokens=* delims= " %%a in ("!x!") do set "x=%%a"
for /l %%a in (1,1,100) do if "!x:~-1!"==" " set "x=!x:~0,-1!"
endlocal & set "%1=%x%"
goto :eof