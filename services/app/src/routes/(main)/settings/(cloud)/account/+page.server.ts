import { env as privateEnv } from '$env/dynamic/private';
import { fail, redirect } from '@sveltejs/kit';
import { ManagementClient } from 'auth0';

const {
	AUTH0_CLIENT_ID,
	AUTH0_ISSUER_BASE_URL,
	AUTH0_MGMTAPI_CLIENT_ID,
	AUTH0_MGMTAPI_CLIENT_SECRET
} = privateEnv;

const management = new ManagementClient({
	domain: AUTH0_ISSUER_BASE_URL?.replace('https://', ''),
	clientId: AUTH0_MGMTAPI_CLIENT_ID,
	clientSecret: AUTH0_MGMTAPI_CLIENT_SECRET
});

export const actions = {
	'change-password': async ({ locals }) => {
		//* Verify user perms
		if (!locals.user) {
			return fail(401, { message: 'Unauthorized' });
		}

		const pwChangeRes = await management.tickets.changePassword({
			user_id: locals.user.sub,
			client_id: AUTH0_CLIENT_ID,
			ttl_sec: 0,
			mark_email_as_verified: false,
			includeEmailInRedirect: true
		});
		if (pwChangeRes.status !== 200 && pwChangeRes.status !== 201) {
			return fail(pwChangeRes.status, {
				message: 'API returned error',
				body: pwChangeRes.data
			});
		} else {
			throw redirect(303, pwChangeRes.data.ticket);
		}
	}
};
