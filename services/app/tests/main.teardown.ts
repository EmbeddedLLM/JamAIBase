import 'dotenv/config';
import fs from 'fs';
import { test as teardown } from '@playwright/test';
import type { UserRead } from '$lib/types';

const { JAMAI_URL, JAMAI_SERVICE_KEY, TEST_ACC_USERID } = process.env;

teardown('delete setup', async () => {
	const headers = {
		Authorization: `Bearer ${JAMAI_SERVICE_KEY}`
	};

	const userInfoRes = await fetch(`${JAMAI_URL}/api/admin/backend/v1/users/${TEST_ACC_USERID}`, {
		headers
	});
	const userInfoBody = await userInfoRes.json();
	if (!userInfoRes.ok) throw new Error(userInfoBody);

	const testOrgs = (userInfoBody as UserRead).member_of.filter((org) =>
		/test-org/.test(org.organization_name)
	);

	if (testOrgs.length === 0) {
		console.warn('Playwright test organization not found, skipping delete step');
	} else {
		for (const testOrg of testOrgs) {
			const deleteOrgRes = await fetch(
				`${JAMAI_URL}/api/admin/backend/v1/organizations/${testOrg?.organization_id}`,
				{
					method: 'DELETE',
					headers
				}
			);
			if (!deleteOrgRes.ok) {
				const deleteOrgBody = await deleteOrgRes.json();
				throw new Error(deleteOrgBody);
			}
		}
	}

	const downloadedFiles = fs.readdirSync('./tests/fixtures');
	for (const file of downloadedFiles) {
		if (file.endsWith('.parquet') || file.startsWith('test-')) {
			fs.rmSync('./tests/fixtures/' + file);
		}
	}
});
