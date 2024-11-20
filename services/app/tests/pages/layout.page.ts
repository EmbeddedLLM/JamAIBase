import 'dotenv/config';
import { expect, type Locator, type Page } from '@playwright/test';

/** Layout with breadcrumbs */
export class LayoutPage {
	readonly page: Page;
	readonly selectOrgBtn: Locator;

	constructor(page: Page) {
		this.page = page;
		this.selectOrgBtn = page.locator('#select-org-btn');
	}

	async switchOrganization(organizationName: string) {
		if (process.env.PUBLIC_IS_LOCAL === 'false') {
			const orgSelector = this.page.getByTestId('org-selector');
			await expect(async () => {
				await this.selectOrgBtn.click();
				await expect(orgSelector).toBeVisible();
			}).toPass();
			await orgSelector
				.locator('div[role="menuitem"]')
				.getByText(organizationName.trim(), { exact: true })
				.click();

			expect((await this.selectOrgBtn.textContent())?.trim()).toBe(organizationName.trim());
		}
	}
}
