import { test as setup } from '@playwright/test';
import 'dotenv/config';
import { existsSync } from 'fs';

const ossMode = !process.env.OWL_SERVICE_KEY;
const authFile = 'playwright/.auth/user.json';

setup('authenticate', async ({ browser, page }) => {
	if (!ossMode) {
		if (existsSync(authFile)) {
			await page.close();
			const context = await browser.newContext({ storageState: authFile });
			page = await context.newPage();
		}

		await page.goto('/');
		const isCredentialsValid = !/.*\/(login)/.test(page.url());

		if (!isCredentialsValid) {
			await page.getByPlaceholder('Username').fill(process.env.TEST_USER_USERNAME!);
			await page.getByPlaceholder('Password').fill(process.env.TEST_USER_PASSWORD!);
			await page.getByRole('button', { name: 'Login', exact: true }).click();
		}

		await page.waitForURL(/.*\/(project|new-organization)/);

		await page.context().storageState({ path: authFile });
	}
});
