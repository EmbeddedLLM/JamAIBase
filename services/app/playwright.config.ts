import type { PlaywrightTestConfig } from '@playwright/test';
import { devices } from '@playwright/test';

const config: PlaywrightTestConfig = {
	webServer: {
		command: 'npm run devstart',
		port: 4173
	},
	testDir: 'tests',
	testMatch: /(.+\.)?(test|spec)\.[jt]s/,
	outputDir: 'playwright/results',
	reporter: [['html', { open: 'always', outputFolder: 'playwright/reports' }]],
	use: {
		screenshot: 'on',
		baseURL: 'http://localhost:4173/'
	},
	projects: [
		// Setup project
		{ name: 'setup', testMatch: /.*\.setup\.ts/ },

		/* {
			name: 'chromium',
			use: {
				...devices['Desktop Chrome'],
				// Use prepared auth state.
				storageState: 'playwright/.auth/user.json'
			},
			dependencies: ['setup']
		}, */

		{
			name: 'chrome',
			use: {
				...devices['Desktop Chrome'],
				storageState: 'playwright/.auth/user.json'
			},
			dependencies: ['setup']
		}
	]
};

export default config;
