import 'dotenv/config';
import { existsSync } from 'fs';
import { test as setup } from '@playwright/test';

const authFile = 'playwright/.auth/user.json';

setup('authenticate', async ({ browser, page }) => {
	if (process.env.PUBLIC_IS_LOCAL === 'false') {
		if (existsSync(authFile)) {
			await page.close();
			const context = await browser.newContext({ storageState: authFile });
			page = await context.newPage();
		}

		await page.goto('/');
		const isCredentialsValid = !/.*\/(login)/.test(page.url());

		if (!isCredentialsValid) {
			await page.getByLabel('Email address').fill(process.env.TEST_ACC_EMAIL!);
			await page.getByLabel('Password').fill(process.env.TEST_ACC_PW!);
			await page.getByRole('button', { name: 'Continue', exact: true }).click();
		}

		await page.goto('/');

		await page.waitForURL(/.*\/(project|new-organization)/);

		await page.context().storageState({ path: authFile });
	}
});
