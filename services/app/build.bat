@echo off
setlocal enabledelayedexpansion

rem Load environment variables from .env file
for /f "usebackq delims==" %%a in (".env") do (
    set "%%a"
)

rem Set the flag variable
set DEV_MODE=1

rem Build the project in /temp
call vite build

rem Copy the build files to the build directory
if exist build rmdir /s /q build
mkdir build
xcopy /s /e /y temp build
rmdir /s /q temp

rem Static adapter doesn't generate files for these pages, breaking nav
if not "%PUBLIC_IS_SPA%" == "false" (
    xcopy /s /e /y /I "build\project\default\action-table" "build\project\default\chat-table"
    xcopy /s /e /y /I "build\project\default\action-table" "build\project\default\knowledge-table"
)

endlocal