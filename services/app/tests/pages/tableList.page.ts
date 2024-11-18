import 'dotenv/config';
import { expect, type Page } from '@playwright/test';
import { LayoutPage } from './layout.page';
import { TablePage } from './table.page';

/** Only to be instantiated in a project */
export class TableListPage extends LayoutPage {
	constructor(page: Page) {
		if (!/.*\/project\/[^/]+\//.test(page.url())) {
			throw new Error('TableListPage must be instantiated in a project');
		}

		super(page);
	}

	/** Go to table list page with tabs */
	async gotoMenu(menu: 'Action Table' | 'Knowledge Table' | 'Chat Table') {
		await this.page.getByTestId('table-type-nav').getByText(menu, { exact: true }).click();
		await this.page.waitForURL(new RegExp(`./project/.*/${menu.toLowerCase().replace(' ', '-')}`));
		await expect(this.page.getByTestId('loading-skeleton')).toHaveCount(0);
		await expect(this.page.getByTestId('loading-spinner')).toHaveCount(0);
	}

	/** Go to table */
	async gotoTable(tableName: string) {
		if (!/.*\/project\/[^/]+\/chat-table/.test(this.page.url())) {
			await this.page
				.locator('a', { has: this.page.getByText(tableName, { exact: true }) })
				.click();
		} else {
			if (
				await this.page
					.locator('a>div>div>span', { has: this.page.getByText(tableName, { exact: true }) })
					.isVisible()
			) {
				await this.page
					.locator('a', { has: this.page.getByText(tableName, { exact: true }) })
					.click();
			} else {
				await this.page
					.locator('button', { has: this.page.getByText(tableName, { exact: true }) })
					.click();
				await this.page
					.locator('a', { has: this.page.getByText(tableName, { exact: true }) })
					.click();
			}
		}

		await this.page.waitForURL(new RegExp(`.*/project/[^/]+/[^\\s/]*-table/${tableName}`));
		await expect(this.page.getByTestId('loading-spinner')).toHaveCount(0);
	}

	/** Export table */
	async exportTable(tableName: string, downloadPath: string) {
		await this.gotoTable(tableName);
		const tablePage = new TablePage(this.page);
		await tablePage.actionsBtn.click();

		const downloadPromise = this.page.waitForEvent('download');
		await this.page
			.getByTestId('table-actions-dropdown')
			.locator('div[role="menuitem"]', {
				has: this.page.getByText('Export table', { exact: true })
			})
			.click();
		const download = await downloadPromise;

		await download.saveAs(downloadPath + download.suggestedFilename());

		return downloadPath + download.suggestedFilename();
	}

	/** Import table */
	async importTable(uploadPath: string, tableName: string) {
		const [fileChooser] = await Promise.all([
			this.page.waitForEvent('filechooser'),
			this.page.getByRole('button', { name: 'Import table' }).click()
		]);
		await fileChooser.setFiles(uploadPath);

		const importTableDialog = this.page.getByTestId('import-table-dialog');
		await expect(importTableDialog).toBeVisible();
		await importTableDialog.getByRole('button', { name: 'Import' }).click();

		await expect(this.page.getByRole('link', { name: tableName })).toBeVisible();
	}

	/** Completes table rename with shared dialog component already triggered */
	async renameTable(tableName: string, newName: string) {
		await this.page
			.locator('a', { has: this.page.getByText(tableName, { exact: true }) })
			.getByTitle('Table settings')
			.click();
		await this.page.locator('div[role="menuitem"]:has-text("Rename table")').click();

		await this.handleRenameDialog(newName);

		await expect(
			this.page.locator('a', { has: this.page.getByText(newName, { exact: true }) })
		).toBeVisible();
		await expect(
			this.page.locator('a', { has: this.page.getByText(tableName, { exact: true }) })
		).not.toBeAttached();
	}

	async handleRenameDialog(newName: string) {
		const renameDialog = this.page.getByTestId('rename-table-dialog');
		await renameDialog.waitFor({ state: 'visible' });
		await renameDialog.locator('input[name="table_id"]').clear();
		await renameDialog.locator('input[name="table_id"]').fill(newName);
		await renameDialog.locator('button:has-text("Save"):visible').click();
		await renameDialog.waitFor({ state: 'hidden' });
	}

	/** Completes table delete with shared dialog component already triggered */
	async deleteTable(tableName: string) {
		await this.page
			.locator('a', { has: this.page.getByText(tableName, { exact: true }) })
			.getByTitle('Table settings')
			.click();
		await this.page.locator('div[role="menuitem"]:has-text("Delete table")').click();

		await this.handleDeleteDialog();

		await expect(
			this.page.locator('a', { has: this.page.getByText(tableName, { exact: true }) })
		).not.toBeAttached();
	}

	async handleDeleteDialog() {
		const deleteDialog = this.page.getByTestId('delete-table-dialog');
		await deleteDialog.waitFor({ state: 'visible' });
		await deleteDialog.locator('button:has-text("Delete"):visible').click();
		await deleteDialog.waitFor({ state: 'hidden' });
	}
}
