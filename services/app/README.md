# JamAI Base Frontend

## Developing

Create a copy of `.env.example` with

```bash
cp .env.example .env
```

Install dependencies with `npm i` and start the dev server `npm run dev`.

### Building Electron app

> [!IMPORTANT]
> Make sure to install the dependencies and copy the `.env.example` before continuing as [shown above](#developing). 
>
> Once copied, change the following values in the `.env` file as shown here:
> ```bash
> PUBLIC_JAMAI_URL="http://localhost:6969"
> PUBLIC_IS_SPA="true"
> CHECK_ORIGIN="false"
> ```

Ensure that all cloud modules are removed from the project by running `scripts/remove_cloud_modules.sh` while in the root directory. Cloud frontend cannot be built into static file for a single-page application. 

The following is an equivalent script that can be run in PowerShell for building on Windows by running `scripts/remove_cloud_modules.ps1`:

```powershell
Get-ChildItem -Recurse -File -Filter "cloud*.py" | Remove-Item -Force
Get-ChildItem -Recurse -File -Filter "compose.*.cloud.yml" | Remove-Item -Force
Get-ChildItem -Recurse -Directory -Filter "(cloud)" | Remove-Item -Recurse -Force
Remove-Item -Force "services/app/ecosystem.config.cjs"
Remove-Item -Force "services/app/ecosystem.json"
```

Next, run the following to build the app in whatever OS you're currently in:

```bash
cd services/app
npm run package
```

The Electron Forge Package command packages the app into platform-specific executables. To create distributables, run `npm run make`. [See docs](https://www.electronforge.io/cli#package#:~:text=Please%20note%20that%20this%20does%20not%20make%20a%20distributable%20format.%20To%20make%20proper%20distributables%2C%20please%20use%20the%20Make%20command.)

Once done, the packaged app will be in `services/app/build-electron`.

[Electron Forge docs](https://www.electronforge.io/config/makers)

## Build Complete JamAIBase Electron App
1. Follow all the steps in [Building Electron app](#building-electron-app). But run the following compilation steps.
    ```powershell
    cd services/app
    npm run make
    ```

2. Extract the compiled zip file:
    ```powershell
    cd .\services\app\build-electron\make\zip\win32\x64
    Expand-Archive -Path 'jamaibase-app-win32-x64-0.2.0.zip' -DestinationPath 'jamaibase-app-win32-x64-0.2.0' -Force
    ```
3. Copy the executable into `services\app\build-electron\make\zip\win32\x64\jamaibase-app-win32-x64-0.2.0` (doing it this way speeds up compilation of the electron app) *Compiling through the electron-forge is too slow*:
    - `infinity_server` (pyinstaller compile all the python services).
    - `ellm_api_server` (pyinstaller compile all the python services).
    - `docio` (pyinstaller compile all the python services).
    - `unstructuredio_api` (pyinstaller compile all the python services).
    - `api` (pyinstaller compile all the python services).

4. Download the embedding model and, reranker model into `services\app\build-electron\make\zip\win32\x64\jamaibase-app-win32-x64-0.2.0`.
    ```powershell
    conda create -n hfcli python=3.10
    conda activate hfcli
    pip install -U "huggingface_hub[cli]"
    cd .\services\app\build-electron\make\zip\win32\x64\jamaibase-app-win32-x64-0.2.0\resources
    huggingface-cli download sentence-transformers/all-MiniLM-L6-v2 --local-dir .\sentence-transformers_all-MiniLM-L6-v2
    huggingface-cli download cross-encoder/ms-marco-TinyBERT-L-2 --local-dir .\cross-encoder_ms-marco-TinyBERT-L-2

    # Windows has limit to the filepath length
    # So download the model in Documents
    huggingface-cli download EmbeddedLLM/Phi-3-mini-4k-instruct-062024-onnx --include="onnx/directml/Phi-3-mini-4k-instruct-062024-int4/*" --local-dir .\llm_model
    # copy the content of # C:\Users\{user}\Documents\llm_model\onnx\directml\Phi-3-mini-4k-instruct-062024-int4
    # into .\services\app\build-electron\make\zip\win32\x64\jamaibase-app-win32-x64-0.2.0\resources\llm_model
    ```
5. The directory structure looks like this
    ```
    jamaibase-app-win32-x64-0.2.0
    |-- resources
        |-- cross-encoder_ms-marco-TinyBERT-L-2
        |-- sentence-transformers_all-MiniLM-L6-v2
        |-- llm_model
        |-- infinity_server
            |-- _internal
            |-- infinity_server.exe
        |-- ellm_api_server
            |-- _internal
            |-- ellm_api_server.exe
        |-- docio
            |-- _internal
            |-- docio.exe
        |-- unstructuredio_api
            |-- _internal
            |-- unstructuredio_api.exe
        |-- api
            |-- _internal
            |-- api.exe
    ```
6. To run the application. Double-click on `jamaibase-app.exe`.

## Build app installer with Innosetup (Windows)
### Prerequisite
* Install [Innosetup](https://jrsoftware.org/isdl.php) from [link](https://jrsoftware.org/isdl.php)

1. [Build a complete JamAIBase Electron App](#build-complete-jamaibase-electron-app)

2. Copy the Innosetup configuration and icon into the unzipped directory:
    ```powershell
    cd .\services\app
    Copy-Item -Path .\JamAIBase.iss -Destination .\build-electron\make\zip\win32\x64\jamaibase-app-win32-x64-0.2.0
    Copy-Item -Path .\electron\icons -Destination .\build-electron\make\zip\win32\x64\jamaibase-app-win32-x64-0.2.0\ -Recurse
    ```
3. Open the `JamAIBase.iss` file using Innosetup.
4. Start building the executable using Innosetup. `Build -> Compile`(`Ctrl+F9`) (Note that to package everything requires a few hours.)
5. After compilation you can find the installation files and resources in `Output` folder under `jamaibase-app-win32-x64-0.2.0`.

## Developer
1. To run the UI in debug mode. `npm run start:debug_electron`.