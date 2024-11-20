import { expect, test } from '@playwright/test';
import { ProjectPage } from './pages/project.page';
import { TableListPage } from './pages/tableList.page';

test.describe.configure({ mode: 'parallel' });

test.describe('Action Table', () => {
	let downloadPath: string;

	test.describe.configure({ mode: 'serial' });

	test.beforeEach(async ({ page }) => {
		const projectPage = new ProjectPage(page);
		await projectPage.goto();
		await projectPage.switchOrganization('test-org');
		await projectPage.gotoProject('test-project');
		await expect(page.getByTestId('loading-skeleton')).toHaveCount(0);
	});

	//TODO: Test adding tables with columns
	test('can add new action table', async ({ page }) => {
		await page.getByLabel('Create table').click();

		const modal = page.getByTestId('new-table-dialog');
		await modal.waitFor({ state: 'visible' });
		await modal.locator('input[name="table_id"]').fill('transient-test-action-table');
		await modal.locator('button:has-text("Create"):visible').click();
		await modal.waitFor({ state: 'hidden' });

		await expect(
			page.locator('a', { has: page.getByText('transient-test-action-table', { exact: true }) })
		).toBeVisible();
	});

	test('can export action table', async ({ page }) => {
		const tableListPage = new TableListPage(page);
		downloadPath = await tableListPage.exportTable(
			'transient-test-action-table',
			'./tests/fixtures/'
		);
	});

	test('can rename action table', async ({ page }) => {
		const tableListPage = new TableListPage(page);
		await tableListPage.renameTable('transient-test-action-table', 'transient-test-table');
	});

	test('can import action table', async ({ page }) => {
		const tableListPage = new TableListPage(page);
		await tableListPage.importTable(downloadPath, 'transient-test-action-table');
	});

	test('can delete action table', async ({ page }) => {
		const tableListPage = new TableListPage(page);
		await tableListPage.deleteTable('transient-test-table');
	});
});

test.describe('Knowledge Table', () => {
	let downloadPath: string;

	test.describe.configure({ mode: 'serial' });

	test.beforeEach(async ({ page }) => {
		const projectPage = new ProjectPage(page);
		await projectPage.goto();
		await projectPage.switchOrganization('test-org');
		await projectPage.gotoProject('test-project');
		const tableListPage = new TableListPage(page);
		await tableListPage.gotoMenu('Knowledge Table');
	});

	//TODO: Test adding tables with columns
	test('can add new knowledge table', async ({ page }) => {
		await page.getByLabel('Create table').click();

		const modal = page.getByTestId('new-table-dialog');
		await modal.waitFor({ state: 'visible' });
		await modal.locator('input[name="table_id"]').fill('transient-test-knowledge-table');
		await modal.getByTestId('model-select-btn').click();
		await modal.getByTestId('model-select-btn').locator('div[role="option"]').first().click();
		await modal.locator('button:has-text("Create"):visible').click();
		await modal.waitFor({ state: 'hidden' });

		await expect(
			page.locator('a', { has: page.getByText('transient-test-knowledge-table', { exact: true }) })
		).toBeVisible();
	});

	test('can export knowledge table', async ({ page }) => {
		const tableListPage = new TableListPage(page);
		downloadPath = await tableListPage.exportTable(
			'transient-test-knowledge-table',
			'./tests/fixtures/'
		);
	});

	test('can rename knowledge table', async ({ page }) => {
		const tableListPage = new TableListPage(page);
		await tableListPage.renameTable('transient-test-knowledge-table', 'transient-test-table');
	});

	test('can import knowledge table', async ({ page }) => {
		const tableListPage = new TableListPage(page);
		await tableListPage.importTable(downloadPath, 'transient-test-knowledge-table');
	});

	test('can delete knowledge table', async ({ page }) => {
		const tableListPage = new TableListPage(page);
		await tableListPage.deleteTable('transient-test-table');
	});
});

test.describe('Chat Table', () => {
	let downloadPath: string;

	test.describe.configure({ mode: 'serial' });

	test.beforeEach(async ({ page }) => {
		const projectPage = new ProjectPage(page);
		await projectPage.goto();
		await projectPage.switchOrganization('test-org');
		await projectPage.gotoProject('test-project');
		const tableListPage = new TableListPage(page);
		await tableListPage.gotoMenu('Chat Table');
	});

	test('can add new chat agent', async ({ page }) => {
		await page.click('button[title="New agent"]');

		const modal = page.getByTestId('new-agent-dialog');
		await modal.waitFor({ state: 'visible' });
		await modal.locator('input[name="agent-id"]').fill('transient-test-chat-agent');
		await modal.locator('button[title="Select model"]').click();
		await modal.locator('div[role="option"]:visible').first().click();
		await modal.locator('button:has-text("Add"):visible').click();
		await modal.waitFor({ state: 'hidden' });

		await expect(
			page
				.getByTestId('agents-list')
				.locator('button', { has: page.getByText('transient-test-chat-agent', { exact: true }) })
		).toBeVisible();
	});

	test('can rename chat agent', async ({ page }) => {
		await page
			.getByTestId('agents-list')
			.locator('button', { has: page.getByText('transient-test-chat-agent', { exact: true }) })
			.click();

		await page.click('button[title="Agent settings"]');
		await page.locator('div[role="menuitem"]', { hasText: 'Rename agent' }).click();

		const tableListPage = new TableListPage(page);
		await tableListPage.handleRenameDialog('transient-test-agent');

		const agentsList = page.getByTestId('agents-list');
		await expect(
			agentsList.locator('button', { has: page.getByText('transient-test-agent', { exact: true }) })
		).toBeVisible();
		await expect(
			agentsList.locator('button', {
				has: page.getByText('transient-test-chat-agent', { exact: true })
			})
		).not.toBeAttached();
	});

	test('can create conversation with chat agent', async ({ page }) => {
		await page.getByLabel('Create table').click();

		const modal = page.getByTestId('new-conv-dialog');
		await modal.waitFor({ state: 'visible' });
		await modal.locator('input[name="conversation-id"]').fill('transient-test-chat-conv');
		await modal.locator('button[title="Select Chat Agent"]').click();
		await modal
			.locator('div[role="option"]:visible', {
				has: page.getByText('transient-test-agent', { exact: true })
			})
			.click();
		expect((await modal.locator('button[title="Select Chat Agent"]').textContent())?.trim()).toBe(
			'transient-test-agent'
		);
		await modal.locator('button:has-text("Add"):visible').click();
		await modal.waitFor({ state: 'hidden' });

		const noOfConvs = await page.getByTestId('conv-list').locator('a').count();
		await page
			.getByTestId('agents-list')
			.locator('button', { has: page.getByText('transient-test-agent', { exact: true }) })
			.click();
		await expect(page.getByTestId('loading-spinner')).toHaveCount(0);

		const convList = page.getByTestId('conv-list');
		expect(await convList.locator('a').count()).toBeLessThanOrEqual(noOfConvs);
		await expect(
			convList.locator('a', { has: page.getByText('transient-test-chat-conv', { exact: true }) })
		).toBeVisible();
	});

	test('can export chat table', async ({ page }) => {
		const tableListPage = new TableListPage(page);
		downloadPath = await tableListPage.exportTable('transient-test-chat-conv', './tests/fixtures/');
	});

	test('can rename chat conversation', async ({ page }) => {
		await page
			.getByTestId('agents-list')
			.locator('button', { has: page.getByText('transient-test-agent', { exact: true }) })
			.click();
		await expect(page.getByTestId('loading-spinner')).toHaveCount(0);

		await page
			.getByTestId('conv-list')
			.locator('a', { has: page.getByText('transient-test-chat-conv', { exact: true }) })
			.locator('button[title="Table settings"]')
			.click();
		await page.locator('div[role="menuitem"]:has-text("Rename table")').click();

		const tableListPage = new TableListPage(page);
		await tableListPage.handleRenameDialog('transient-test-conv');

		const convList = page.getByTestId('conv-list');
		await expect(
			convList.locator('a', { has: page.getByText('transient-test-conv', { exact: true }) })
		).toBeVisible();
		await expect(
			convList.locator('a', { has: page.getByText('transient-test-chat-conv', { exact: true }) })
		).not.toBeAttached();
	});

	test('can import knowledge table', async ({ page }) => {
		const tableListPage = new TableListPage(page);
		await tableListPage.importTable(downloadPath, 'transient-test-chat-conv');
	});

	test('can delete chat conversation', async ({ page }) => {
		await page
			.getByTestId('agents-list')
			.locator('button', { has: page.getByText('transient-test-agent', { exact: true }) })
			.click();
		await expect(page.getByTestId('loading-spinner')).toHaveCount(0);

		await page
			.getByTestId('conv-list')
			.locator('a', { has: page.getByText('transient-test-conv', { exact: true }) })
			.locator('button[title="Table settings"]')
			.click();
		await page.locator('div[role="menuitem"]:has-text("Delete table")').click();

		const tableListPage = new TableListPage(page);
		await tableListPage.handleDeleteDialog();

		await expect(
			page
				.getByTestId('conv-list')
				.locator('a', { has: page.getByText('transient-test-conv', { exact: true }) })
		).not.toBeAttached();
	});

	test('can delete chat agent', async ({ page }) => {
		await page
			.getByTestId('agents-list')
			.locator('button', { has: page.getByText('transient-test-agent', { exact: true }) })
			.click();
		await expect(page.getByTestId('loading-spinner')).toHaveCount(0);

		await page.click('button[title="Agent settings"]');
		await page.locator('div[role="menuitem"]', { hasText: 'Delete agent' }).click();

		const tableListPage = new TableListPage(page);
		await tableListPage.handleDeleteDialog();

		await expect(
			page
				.getByTestId('agents-list')
				.locator('button', { has: page.getByText('transient-test-agent', { exact: true }) })
		).not.toBeAttached();
	});
});
