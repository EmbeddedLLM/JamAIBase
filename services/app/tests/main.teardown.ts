import type { User } from '$lib/types';
import { test as teardown } from '@playwright/test';
import 'dotenv/config';
import fs from 'fs';

const { OWL_URL, OWL_SERVICE_KEY, TEST_USER_ID } = process.env;

teardown('delete setup', async () => {
	const headers = {
		Authorization: `Bearer ${OWL_SERVICE_KEY}`
	};

	const userInfoRes = await fetch(
		`${OWL_URL}/api/v2/users?${new URLSearchParams([['user_id', TEST_USER_ID!]])}`,
		{
			headers: {
				...headers,
				'x-user-id': process.env.TEST_USER_ID!
			}
		}
	);
	const userInfoBody = await userInfoRes.json();
	if (!userInfoRes.ok) throw JSON.stringify(userInfoBody);

	const testOrgs = (userInfoBody as User).organizations.filter((org) => /test-org/.test(org.name));

	if (testOrgs.length === 0) {
		console.warn('Playwright test organization not found, skipping delete step');
	} else {
		for (const testOrg of testOrgs) {
			const deleteOrgRes = await fetch(
				`${OWL_URL}/api/v2/organizations?${new URLSearchParams([['organization_id', testOrg.id]])}`,
				{
					method: 'DELETE',
					headers: {
						...headers,
						'x-user-id': process.env.TEST_USER_ID!
					}
				}
			);
			if (!deleteOrgRes.ok) {
				const deleteOrgBody = await deleteOrgRes.json();
				throw JSON.stringify(deleteOrgBody);
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
