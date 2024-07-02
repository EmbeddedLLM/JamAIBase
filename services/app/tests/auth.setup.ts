import 'dotenv/config';
import { existsSync } from 'fs';
import { test as setup } from '@playwright/test';

const authFile = 'playwright/.auth/user.json';

setup('authenticate', async ({ browser, page }) => {
	// Check if the authentication file exists.
	if (!existsSync(authFile)) {
		await page.goto('/login');
		await page.getByLabel('Email address*').fill(process.env.TEST_ACC_EMAIL!);
		await page.getByLabel('Password*').fill(process.env.TEST_ACC_PW!);
		await page.getByRole('button', { name: 'Continue', exact: true }).click();
	} else {
		await page.close();
		const context = await browser.newContext({ storageState: authFile });
		page = await context.newPage();
	}

	await page.goto('/project');

	await page.waitForURL('http://localhost:4173/project');

	await page.context().storageState({ path: authFile });
});
