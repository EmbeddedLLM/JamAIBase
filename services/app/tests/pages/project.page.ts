import { expect, type Page } from '@playwright/test';
import 'dotenv/config';
import { LayoutPage } from './layout.page';

const ossMode = !process.env.OWL_SERVICE_KEY;

export class ProjectPage extends LayoutPage {
	constructor(page: Page) {
		super(page);
	}

	async goto() {
		if (!ossMode) {
			await this.page.goto('/');
			await this.page.waitForURL(/.*\/project/);
		} else {
			await this.page.goto('/project/default');
			await this.page.waitForURL(/.*\/project\/default/);
		}
	}

	async gotoProject(projectName: string) {
		if (!ossMode) {
			await this.page
				.locator('a', { has: this.page.getByText(projectName, { exact: true }) })
				.click();
			await this.page.waitForURL(/.*\/project\/[^/]+\/action-table/);
		}
	}

	async addNewProject(projectName: string) {
		await this.page.click('button:has-text("New Project")');

		const newProjectDialog = this.page.getByTestId('new-project-dialog');
		await newProjectDialog.locator('input[name="project_name"]').fill(projectName);
		await newProjectDialog.locator('button:has-text("Create")').click();
		await newProjectDialog.waitFor({ state: 'hidden' });

		await expect(
			this.page.locator('a', { has: this.page.getByText(projectName, { exact: true }) })
		).toBeVisible();
	}

	async renameProject(projectName: string, renameTo: string) {
		await this.page
			.locator('a', { has: this.page.getByText(projectName) })
			.getByTitle('Project settings')
			.click();

		await this.page
			.getByTestId('project-settings-dropdown')
			.getByRole('menuitem', { name: 'Rename project' })
			.click();

		const renameProjDialog = this.page.getByTestId('rename-project-dialog');
		await expect(renameProjDialog).toBeVisible();

		await renameProjDialog.getByLabel('Project name').clear();
		await renameProjDialog.getByLabel('Project name').fill(renameTo);
		await renameProjDialog
			.locator('button:visible', { has: this.page.getByText('Save', { exact: true }) })
			.click();
		await renameProjDialog.waitFor({ state: 'hidden' });

		await expect(
			this.page.locator('a', { has: this.page.getByText(projectName) })
		).not.toBeVisible();
	}

	async deleteProject(projectName: string) {
		await this.page
			.locator('a', { has: this.page.getByText(projectName, { exact: true }) })
			.getByTitle('Project settings')
			.click();
		await this.page.locator('div[role="menuitem"]:has-text("Delete project")').click();

		const modal = this.page.getByTestId('delete-project-dialog');
		await modal.waitFor({ state: 'visible' });
		await modal.locator('input[name="project_name"]').fill(projectName);
		await modal.locator('button:has-text("Delete")').click();
		await modal.waitFor({ state: 'hidden' });

		await expect(
			this.page.locator('a', { has: this.page.getByText(projectName, { exact: true }) })
		).not.toBeAttached();
	}
}

export class ActionTablePage extends LayoutPage {
	constructor(page: Page) {
		super(page);
	}
}
