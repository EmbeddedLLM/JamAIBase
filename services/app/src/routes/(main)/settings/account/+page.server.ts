import { env } from '$env/dynamic/private';
import logger, { APIError } from '$lib/logger.js';
import type { PATRead } from '$lib/types.js';
import { fail, redirect } from '@sveltejs/kit';
import { ManagementClient } from 'auth0';

const {
	AUTH0_CLIENT_ID,
	AUTH0_ISSUER_BASE_URL,
	AUTH0_MGMTAPI_CLIENT_ID,
	AUTH0_MGMTAPI_CLIENT_SECRET,
	OWL_SERVICE_KEY,
	OWL_URL
} = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

const management = new ManagementClient({
	domain: AUTH0_ISSUER_BASE_URL?.replace('https://', ''),
	clientId: AUTH0_MGMTAPI_CLIENT_ID,
	clientSecret: AUTH0_MGMTAPI_CLIENT_SECRET
});

export async function load({ locals }) {
	//TODO: Infinite scroll this
	const getPats = async () => {
		const patListRes = await fetch(`${OWL_URL}/api/v2/pats/list`, {
			headers: {
				...headers,
				'x-user-id': locals.user?.id ?? ''
			}
		});
		const patListBody = await patListRes.json();

		if (!patListRes.ok) {
			logger.error('PAT_LIST_ERROR', patListBody);
			return { error: patListRes.status, message: patListBody };
		} else {
			return {
				data: patListBody.items as PATRead[]
			};
		}
	};

	return {
		pats: await getPats()
	};
}

export const actions = {
	'change-password': async ({ locals, request }) => {
		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		if (locals.auth0Mode) {
			try {
				const pwChangeRes = await management.tickets.changePassword({
					user_id: locals.user.sub,
					client_id: AUTH0_CLIENT_ID,
					ttl_sec: 0,
					mark_email_as_verified: false,
					includeEmailInRedirect: true
				});
				if (pwChangeRes.status !== 200 && pwChangeRes.status !== 201) {
					return fail(
						pwChangeRes.status,
						new APIError('Failed to change password', pwChangeRes as any).getSerializable()
					);
				} else {
					throw redirect(303, pwChangeRes.data.ticket);
				}
			} catch (err) {
				//@ts-expect-error library throws error for redirects???
				if (err?.status === 303) {
					//@ts-expect-error see above
					throw redirect(303, err.location);
				} else {
					logger.error('PASSWORD_CHANGE_CHANGE', err);
					return fail(500, new APIError('Failed to change password', err as any).getSerializable());
				}
			}
		} else {
			try {
				const data = await request.formData();
				const password = data.get('password');
				const new_password = data.get('new_password');

				if (
					!password ||
					typeof password !== 'string' ||
					!new_password ||
					typeof new_password !== 'string'
				) {
					return fail(400, new APIError('Invalid form data').getSerializable());
				}

				const response = await fetch(`${OWL_URL}/api/v2/auth/login/password`, {
					method: 'PATCH',
					headers: {
						...headers,
						'Content-Type': 'application/json',
						'x-user-id': locals.user.id
					},
					body: JSON.stringify({
						email: locals.user.email,
						password,
						new_password
					})
				});

				const responseData = await response.json();

				if (!response.ok) {
					logger.error('PASSWORD_CHANGE_ERROR', responseData, locals.user.email || locals.user.id);
					return fail(
						response.status,
						new APIError('Failed to change password', responseData).getSerializable()
					);
				}

				return responseData;
			} catch (err) {
				logger.error('PASSWORD_CHANGE_ERROR', err);
				return fail(500, new APIError('Failed to change password', err as any).getSerializable());
			}
		}
	},

	'create-pat': async ({ locals, request }) => {
		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		const data = await request.formData();
		const patName = data.get('pat_name');
		const patExpiry = data.get('pat_expiry');
		const patProject = data.get('pat_project');

		if (
			typeof patName !== 'string' ||
			typeof patExpiry !== 'string' ||
			typeof patProject !== 'string'
		) {
			return fail(400, new APIError('Invalid form data').getSerializable());
		}

		const patCreateRes = await fetch(`${OWL_URL}/api/v2/pats`, {
			method: 'POST',
			headers: {
				...headers,
				'x-user-id': locals.user?.id,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				name: patName,
				expiry: patExpiry || null,
				project_id: patProject || null
			})
		});
		const patCreateBody = await patCreateRes.json();

		if (patCreateRes.ok) {
			return patCreateBody;
		} else {
			return fail(
				patCreateRes.status,
				new APIError('Failed to create PAT', patCreateBody as any).getSerializable()
			);
		}
	},

	'delete-pat': async ({ locals, request }) => {
		const data = await request.formData();
		const key = data.get('key');

		if (typeof key !== 'string' || key.trim() === '') {
			return fail(400, new APIError('Invalid PAT').getSerializable());
		}

		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		const patDeleteRes = await fetch(
			`${OWL_URL}/api/v2/pats?${new URLSearchParams([['pat_id', key]])}`,
			{
				method: 'DELETE',
				headers: {
					...headers,
					'x-user-id': locals.user?.id
				}
			}
		);
		const patDeleteBody = await patDeleteRes.json();

		if (patDeleteRes.ok) {
			return patDeleteBody;
		} else {
			return fail(
				patDeleteRes.status,
				new APIError('Failed to delete PAT', patDeleteBody as any).getSerializable()
			);
		}
	},

	'delete-account': async ({ locals }) => {
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		const deleteUserRes = await fetch(`${OWL_URL}/api/v2/users`, {
			method: 'DELETE',
			headers: {
				...headers,
				'x-user-id': locals.user.id
			}
		});

		const deleteUserBody = await deleteUserRes.json();
		if (!deleteUserRes.ok) {
			logger.error('USER_DELETE_DELETE', deleteUserBody);
			return fail(
				deleteUserRes.status,
				new APIError('Failed to delete account', deleteUserBody as any).getSerializable()
			);
		} else {
			return deleteUserBody;
		}
	}
};
