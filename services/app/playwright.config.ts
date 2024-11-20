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
	reporter: [['html', { open: 'never', outputFolder: 'playwright/reports' }]],
	use: {
		screenshot: 'on',
		baseURL: 'http://localhost:4173/'
	},
	projects: [
		{ name: 'auth-setup', testMatch: /auth\.setup\.ts/ },
		{
			name: 'main-setup',
			testMatch: /main\.setup\.ts/,
			teardown: 'cleanup',
			dependencies: ['auth-setup']
		},
		{ name: 'cleanup', testMatch: /main\.teardown\.ts/ },

		//* main
		{
			name: 'chrome',
			use: {
				...devices['Desktop Chrome'],
				storageState: 'playwright/.auth/user.json'
			},
			dependencies: ['main-setup']
		}
		// {
		// 	name: 'firefox',
		// 	use: {
		// 		...devices['Desktop Firefox'],
		// 		storageState: 'playwright/.auth/user.json'
		// 	},
		// 	dependencies: ['main-setup']
		// },
		// {
		// 	name: 'webkit',
		// 	use: {
		// 		...devices['Desktop Safari'],
		// 		storageState: 'playwright/.auth/user.json'
		// 	},
		// 	dependencies: ['main-setup']
		// }
	],
	retries: 2,
	timeout: 45_000,
	expect: {
		timeout: 10_000
	}
};

export default config;
