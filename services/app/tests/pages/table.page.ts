import 'dotenv/config';
import { expect, type Locator, type Page } from '@playwright/test';
import { LayoutPage } from './layout.page';
import type { genTableDTypes } from '$lib/constants';

/** Only to be instantiated in a project */
export class TablePage extends LayoutPage {
	readonly titleRow: Locator;
	readonly tableArea: Locator;
	readonly tableHeader: Locator;
	readonly rows: Locator;
	readonly tablePagination: Locator;
	readonly actionsBtn: Locator;

	constructor(page: Page) {
		if (!/.*\/project\/[^/]+\/[^/]+-table/.test(page.url())) {
			throw new Error('TablePage must be instantiated in a project');
		}

		super(page);
		this.titleRow = page.getByTestId('table-title-row');
		this.tableArea = page.getByTestId('table-area');
		this.tableHeader = this.tableArea.locator('div[role="row"]:has(div[role="columnheader"])');
		this.rows = this.tableArea.locator('div[role="row"]:has(div[role="gridcell"])');
		this.tablePagination = page.getByTestId('table-pagination');
		this.actionsBtn = page.getByTitle('Table actions');
	}

	/** Open column settings by zero based index */
	async openColumnSettings(n: number) {
		await this.tableHeader
			.locator('div[role="columnheader"]')
			.nth(n)
			.locator('button[title="Column actions"]')
			.click();
		await this.page.locator('div[role="menuitem"]', { hasText: 'Open settings' }).click();

		await expect(this.page.getByTestId('column-settings-area')).toBeVisible();
	}

	/** Update column settings prompt */
	async updateColumnPrompt(idx: number, prompt: string) {
		await this.openColumnSettings(idx);

		const columnSettings = this.page.getByTestId('column-settings-area');
		const promptInput = columnSettings.locator('textarea');
		// const defaultValue = await promptInput.inputValue();

		await promptInput.fill(prompt);
		await this.page
			.locator('button', { has: this.page.getByText('Update', { exact: true }) })
			.click();
		await expect(columnSettings).not.toBeVisible();

		await this.openColumnSettings(idx);
		await expect(columnSettings).toBeVisible();

		// expect((await promptInput.inputValue()).trim()).not.toEqual(defaultValue);
		expect((await promptInput.inputValue()).trim()).toEqual(prompt);
	}

	async closeColumnSettings() {
		this.page.on('dialog', (dialog) => dialog.accept());
		await this.page
			.getByTestId('column-settings-area')
			.locator('button:has-text("Cancel")')
			.click();
	}

	/** Generate outputs */
	async generate() {
		await this.page
			.locator('button', { has: this.page.getByText('Generate', { exact: true }) })
			.click();
	}

	/** Add new row */
	async addRow(input: { type: 'str' | 'file'; value: string }) {
		const previousRowCount = await this.rows.count();
		const inlineNewRowRow = this.tableArea.locator('form[role="row"]');
		await inlineNewRowRow.click();

		if (input.type === 'str') {
			await inlineNewRowRow.locator('textarea').first().fill(input.value);
			await inlineNewRowRow.locator('textarea').first().press('Enter');
		} else {
			const fileColIdx = (
				await this.tableHeader.getByRole('columnheader').allInnerTexts()
			).findIndex((val) => /input\sfile/i.test(val));
			const fileCell = inlineNewRowRow.getByRole('gridcell').nth(fileColIdx - 1);
			const [fileChooser] = await Promise.all([
				this.page.waitForEvent('filechooser'),
				fileCell.locator('button').click()
			]);
			await fileChooser.setFiles(input.value);

			// wait for image to be uploaded in selector
			await expect(fileCell.locator('img')).toBeVisible();

			await inlineNewRowRow.getByTitle('Add row').click();
		}

		expect(await this.rows.count()).toBe(previousRowCount + 1);
		await expect(this.rows.first()).toHaveAttribute('data-streaming', 'true');
		await expect(this.rows.first()).not.toHaveAttribute('data-streaming', { timeout: 15_000 });
		if (input.type === 'file') {
			await expect(this.rows.first().locator('img')).toBeVisible({ timeout: 10_000 });
		}
	}

	/** Edit cell */
	async editCellValue(rowIdx: number, colIdx: number, value: string) {
		const row = this.rows.nth(rowIdx);
		const cell = row.getByRole('gridcell').nth(colIdx);

		await cell.dblclick();
		await expect(cell).toHaveAttribute('data-editing', 'true');
		const cellEditInput = cell.locator('textarea');
		await expect(cellEditInput).toBeVisible();

		const originalValue = await cellEditInput.inputValue();
		cellEditInput.clear();
		cellEditInput.fill(value);
		cellEditInput.focus();
		cellEditInput.press('Enter');

		await expect(cell).not.toHaveAttribute('data-editing');
		expect((await cell.textContent())?.trim()).not.toEqual(originalValue);
		expect((await cell.textContent())?.trim()).toEqual(value);
	}

	/** Edit file cell */
	async editFileColCell(cell: Locator, file: string) {
		await cell.dblclick();
		const [fileChooser] = await Promise.all([
			this.page.waitForEvent('filechooser'),
			cell.locator('button').click()
		]);
		await fileChooser.setFiles(file);

		// wait for image to be uploaded in selector
		await expect(cell.locator('img')).toBeVisible();
	}

	/** Delete file */
	async deleteFile(cell: Locator) {
		await expect(cell.locator('img')).toBeVisible();
		cell.getByRole('button', { name: 'Delete file' }).click();

		const deleteFileModal = this.page.getByTestId('delete-file-dialog');
		await deleteFileModal.waitFor({ state: 'visible' });
		await deleteFileModal
			.locator('button', { has: this.page.getByText('Delete', { exact: true }) })
			.click();
		await deleteFileModal.waitFor({ state: 'hidden' });

		await expect(cell.locator('img')).not.toBeVisible();
	}

	/** Delete file in preview */
	async deleteFileInPreview(cell: Locator) {
		await expect(cell.locator('img')).toBeVisible();

		await cell.getByRole('button', { name: 'Enlarge file' }).click();
		const filePreview = this.page.getByTestId('file-preview');
		await expect(filePreview).toBeVisible();

		await filePreview.getByTitle('Delete file').click();

		const deleteFileModal = this.page.getByTestId('delete-file-dialog');
		await deleteFileModal.waitFor({ state: 'visible' });
		await deleteFileModal
			.locator('button', { has: this.page.getByText('Delete', { exact: true }) })
			.click();
		await deleteFileModal.waitFor({ state: 'hidden' });

		await expect(cell.locator('img')).not.toBeVisible();
	}

	/** Delete rows after selection */
	async deleteRows() {
		expect(await this.rows.locator('button[aria-checked="true"]').count()).toBeGreaterThan(0);
		await this.page
			.locator('button', { has: this.page.getByText('Delete row(s)', { exact: true }) })
			.click();

		const deleteRowModal = this.page.getByTestId('delete-row-dialog');
		await deleteRowModal.waitFor({ state: 'visible' });
		await deleteRowModal.locator('button:has-text("Delete"):visible').click();
		await deleteRowModal.waitFor({ state: 'hidden' });
	}

	/** Add column */
	async addColumn(type: 'input' | 'output', datatype: (typeof genTableDTypes)[number] = 'str') {
		await this.actionsBtn.click();
		await this.page
			.getByTestId('table-actions-dropdown')
			.locator('div[role="menuitem"]', {
				has: this.page.getByText(`Add ${type} column`, { exact: true })
			})
			.click();

		const newColDialog = this.page.getByTestId('new-column-dialog');
		await expect(newColDialog.getByTestId('dialog-header')).toContainText(`New ${type} column`);

		await newColDialog.getByLabel('Column ID').fill(`transient-${type}-column`);
		await newColDialog.getByTestId('datatype-select-btn').click();
		if (type === 'input') {
			await newColDialog
				.getByTestId('datatype-select-btn')
				.locator('div[role="option"]', { hasText: datatype })
				.click();
		}
		if (type === 'output') {
			await newColDialog.getByLabel('Customize prompt').fill('Hello, what is your favorite food?');
		}
		await newColDialog.locator('button:has-text("Add"):visible').click();

		const newColumn = this.tableHeader.locator('[role="columnheader"]', {
			hasText: `transient-${type}-column`
		});
		await expect(newColumn).toBeVisible();
		await expect(newColumn).toContainText(new RegExp(`${type}\\s*${datatype}`, 'i'));
	}

	/** Rename column inline */
	async renameColumnInline(column: Locator, value: string) {
		const initialText = new RegExp((await column.innerText()).replaceAll('\n', '\\s*'), 'i');
		await expect(this.tableHeader).toContainText(initialText);
		await column.dblclick();
		//FIXME: Change this locator to something user visible
		await expect(this.page.locator('#column-id-edit')).toBeVisible();

		await this.page.locator('#column-id-edit').clear();
		await this.page.locator('#column-id-edit').fill(value);
		await this.page.locator('#column-id-edit').press('Enter');

		await expect(this.page.locator('#column-id-edit')).not.toBeVisible();
		await expect(this.tableHeader).not.toContainText(initialText);
	}

	async renameColumnMenu(column: Locator, value: string) {
		const initialText = new RegExp((await column.innerText()).replaceAll('\n', '\\s*'), 'i');
		await column.getByTitle('Column actions').click();

		await this.page
			.getByTestId('column-actions-dropdown')
			.getByRole('menuitem', { name: /Rename/ })
			.click();

		//FIXME: Change this locator to something user visible
		await this.page.locator('#column-id-edit').clear();
		await this.page.locator('#column-id-edit').fill(value);
		await this.page.locator('#column-id-edit').press('Enter');

		await expect(this.page.locator('#column-id-edit')).not.toBeVisible();
		await expect(this.tableHeader).not.toContainText(initialText);
	}

	async reorderColumns(source: string, target: string) {
		const sourceColHeader = this.tableHeader.locator('[role="columnheader"]', {
			has: this.page.getByText(source, { exact: true })
		});
		const targetColHeader = this.tableHeader.locator('[role="columnheader"]', {
			has: this.page.getByText(target, { exact: true })
		});

		const initialSourceIdx = (
			await this.tableHeader.getByRole('columnheader').allInnerTexts()
		).findIndex((val) => new RegExp(source).test(val));

		await sourceColHeader.getByTitle('Drag to reorder columns').hover();
		await this.page.mouse.down();
		await this.page.mouse.move(200, 200);
		await expect(this.page.getByTestId('dragged-column')).toBeVisible();
		await targetColHeader.hover();
		await targetColHeader.hover();
		await this.page.mouse.up();

		await expect(sourceColHeader.getByTitle('Drag to reorder columns')).toBeEnabled();
		const reorderedSourceIdx = (
			await this.tableHeader.getByRole('columnheader').allInnerTexts()
		).findIndex((val) => new RegExp(source).test(val));
		expect(reorderedSourceIdx).toEqual(initialSourceIdx + 1);
	}

	async deleteColumn(column: string) {
		const targetColHeader = this.tableHeader.locator('[role="columnheader"]', {
			has: this.page.getByText(column, { exact: true })
		});
		await targetColHeader.getByTitle('Column actions').click();

		const colOptions = this.page.getByTestId('column-actions-dropdown');
		await colOptions.getByRole('menuitem', { name: /Delete column/ }).click();

		const deleteColModal = this.page.getByTestId('delete-column-dialog');
		await deleteColModal.waitFor({ state: 'visible' });
		await deleteColModal
			.locator('button', { has: this.page.getByText('Delete', { exact: true }) })
			.click();
		await deleteColModal.waitFor({ state: 'hidden' });

		await expect(targetColHeader).not.toBeVisible();
	}
}
