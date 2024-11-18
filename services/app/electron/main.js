/* eslint-disable @typescript-eslint/no-var-requires */
import { app, BrowserWindow } from 'electron';
import { spawn } from 'child_process';
import path from 'path';
import serve from 'electron-serve';

const loadURL = serve({ directory: 'build' });

let childProcesses = [];

const createWindow = () => {
	// Create the browser window.
	let mainWindow = new BrowserWindow({
		width: 800,
		minWidth: 800,
		height: 600,
		minHeight: 600,
		title: 'JamAI Base'
	});

	mainWindow.on('page-title-updated', (e) => {
		e.preventDefault();
	});

	mainWindow.removeMenu();

	loadURL(mainWindow);

	// mainWindow.webContents.openDevTools()

	mainWindow.on('closed', () => {
		terminateChildProcesses();
	});
};

function spawnChildProcess(config) {
	const child = spawn(config.cmd[0], config.cmd.slice(1), { cwd: config.cwd });

	child.on('exit', (code, signal) => {
		console.log(`Child process ${config.cmd[0]} exited with code ${code} and signal ${signal}`);
		terminateChildProcesses();
		app.quit();
	});

	child.on('error', (err) => {
		console.error(`Failed to start child process ${config.cmd[0]}: ${err}`);
	});

	childProcesses.push(child);
}

function terminateChildProcesses() {
	childProcesses.forEach((child) => {
		child.kill();
	});
	childProcesses = [];
}

app.whenReady().then(() => {
	createWindow();

	app.on('activate', () => {
		if (BrowserWindow.getAllWindows().length === 0) createWindow();
	});

	const pyinstallerExecutables = {
		// embedding: {
		// 	cmd: [path.resolve('resources/infinity_server/infinity_server.exe'), 'v1', '--host', '127.0.0.1', '--port', '6909', '--model-warmup', '--device', 'cpu', '--model-name-or-path', 'sentence-transformers/all-MiniLM-L6-v2'],
		// 	cwd: path.resolve('resources/infinity_server'),
		// },
		// reranker: {
		// 	cmd: [path.resolve('resources/infinity_server/infinity_server.exe'), 'v1', '--host', '127.0.0.1', '--port', '6919', '--model-warmup', '--device', 'cpu', '--model-name-or-path', 'cross-encoder/ms-marco-TinyBERT-L-2'],
		// 	cwd: path.resolve('resources/infinity_server'),
		// },
		// ellm_api_server: {
		// 	cmd: [path.resolve('resources/ellm_api_server/ellm_api_server.exe'), '--model_path', path.resolve('resources/phi3-mini-directml-int4-awq-block-128'), '--port', '5555'],
		// 	cwd: path.resolve('resources'),
		// },
		// docio: {
		// 	cmd: [path.resolve('resources/docio/docio.exe'), "--docio_workers", "1", "--docio_host", "127.0.0.1"],
		// 	cwd: path.resolve('resources/docio'),
		// },
		// unstructuredio_api: {
		// 	cmd: [path.resolve('resources/unstructuredio_api/unstructuredio_api.exe')],
		// 	cwd: path.resolve('resources/unstructuredio_api'),
		// },
		// api: {
		// 	cmd: [
		// 		path.resolve('resources/api/api.exe'), 
		// 		"--owl_workers", "1", 
		// 		"--owl_host", "127.0.0.1", 
		// 		"--owl_port", "6969", 
		// 		"--docio_url", "http://127.0.0.1:6979/api/docio", 
		// 		"--unstructuredio_url", "http://127.0.0.1:6989", 
		// 		"--owl_models_config", path.resolve('resources/api/_internal/owl/configsmodels_aipc.json')
		// 	],
		// 	cwd: path.resolve('resources/api'),
		// },
	};


	const checkFileExists = (filePath) => {
		return new Promise((resolve) => {
			fs.access(filePath, fs.constants.F_OK, (err) => {
				resolve(!err);
			});
		});
	};

	const checkAllResources = async () => {
		for (const key in pyinstallerExecutables) {
			const executable = pyinstallerExecutables[key];
			const filePath = executable.cmd[0]; // The first element in the cmd array is the executable path
			const exists = await checkFileExists(filePath);
			if (!exists) {
				console.error(`File not found: ${filePath}`);
				return false;
			}
		}
		return true;
	};

	checkAllResources().then((allExist) => {
		if (allExist) {
			for (const key in pyinstallerExecutables) {
				spawnChildProcess(pyinstallerExecutables[key]);
			}
		} else {
			console.error('One or more resources do not exist.');
		}
	});

});

app.on('window-all-closed', () => {
	if (process.platform !== 'darwin') app.quit();
});