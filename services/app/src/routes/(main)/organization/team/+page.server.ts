import { env } from '$env/dynamic/private';
import { userRoles } from '$lib/constants.js';
import logger, { APIError } from '$lib/logger.js';
import { fail } from '@sveltejs/kit';

const { ORIGIN, OWL_SERVICE_KEY, OWL_URL, RESEND_API_KEY } = env;

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export const actions = {
	invite: async ({ cookies, fetch, locals, request }) => {
		const data = await request.formData();
		const user_email = data.get('user_email');
		const user_role = data.get('user_role');
		const valid_days = data.get('valid_days');
		const activeOrganizationId = cookies.get('activeOrganizationId');

		if (typeof user_email !== 'string' || user_email.trim() === '') {
			return fail(400, new APIError('Invalid user email').getSerializable());
		}

		if (
			typeof user_role !== 'string' ||
			user_role.trim() === '' ||
			!userRoles.includes(user_role as (typeof userRoles)[number])
		) {
			return fail(400, new APIError('Invalid user role').getSerializable());
		}

		if (
			typeof valid_days !== 'string' ||
			valid_days.trim() === '' ||
			isNaN(Number(valid_days)) ||
			Number(valid_days) <= 0
		) {
			return fail(400, new APIError('Invalid valid days').getSerializable());
		}

		if (!activeOrganizationId) {
			return fail(400, new APIError('No active organization').getSerializable());
		}

		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		const getInviteToken = await fetch(
			`${OWL_URL}/api/v2/organizations/invites?${new URLSearchParams({
				user_email: user_email.trim(),
				organization_id: activeOrganizationId,
				role: user_role,
				valid_days
			})}`,
			{
				method: 'POST',
				headers: {
					...headers,
					'x-user-id': locals.user.id
				}
			}
		);
		const inviteToken = await getInviteToken.json();

		if (!getInviteToken.ok) {
			if (![403].includes(getInviteToken.status)) {
				logger.error('ORGTEAM_INVITE_TOKEN', inviteToken);
			}
			return fail(
				getInviteToken.status,
				new APIError('Failed to get invite token', inviteToken as any).getSerializable()
			);
		}

		if (RESEND_API_KEY) {
			const sendEmailRes = await fetch('https://api.resend.com/emails', {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${RESEND_API_KEY}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					from: 'JamAI Base <no-reply@jamaibase.com>',
					to: user_email,
					subject: 'You have been invited to join an organization on JamAI Base',
					html: getInviteEmailBody(locals.user.email, inviteToken.id)
				})
			});

			if (!sendEmailRes.ok) {
				logger.error('ORGTEAM_INVITE_EMAIL', await sendEmailRes.json());
				return fail(sendEmailRes.status, new APIError('Failed to send email').getSerializable());
			}
		}

		return RESEND_API_KEY ? { ok: true } : inviteToken;
	},

	update: async ({ cookies, fetch, locals, request }) => {
		const data = await request.formData();
		const user_id = data.get('user_id');
		const user_role = data.get('user_role');
		const activeOrganizationId = cookies.get('activeOrganizationId');

		if (typeof user_id !== 'string' || user_id.trim() === '') {
			return fail(400, new APIError('Invalid user ID').getSerializable());
		}
		if (
			typeof user_role !== 'string' ||
			user_role.trim() === '' ||
			!userRoles.includes(user_role as (typeof userRoles)[number])
		) {
			return fail(400, new APIError('Invalid user role').getSerializable());
		}

		if (!activeOrganizationId) {
			return fail(400, new APIError('No active organization').getSerializable());
		}

		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		const updateRoleRes = await fetch(
			`${OWL_URL}/api/v2/organizations/members/role?${new URLSearchParams([
				['user_id', user_id],
				['organization_id', activeOrganizationId],
				['role', user_role]
			])}`,
			{
				method: 'PATCH',
				headers: {
					...headers,
					'x-user-id': locals.user.id
				}
			}
		);

		const updateRoleBody = await updateRoleRes.json();
		if (!updateRoleRes.ok) {
			logger.error('ORGTEAM_UPDATE_ROLE', updateRoleBody);
			return fail(
				updateRoleRes.status,
				new APIError('Failed to update role', updateRoleBody as any).getSerializable()
			);
		} else {
			return updateRoleBody;
		}
	},

	remove: async ({ cookies, fetch, locals, request }) => {
		const data = await request.formData();
		const user_id = data.get('user_id');
		const activeOrganizationId = cookies.get('activeOrganizationId');

		if (typeof user_id !== 'string' || user_id.trim() === '') {
			return fail(400, new APIError('Invalid user ID').getSerializable());
		}

		if (!activeOrganizationId) {
			return fail(400, new APIError('No active organization').getSerializable());
		}

		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		const leaveOrgRes = await fetch(
			`${OWL_URL}/api/v2/organizations/members?${new URLSearchParams([
				['user_id', user_id],
				['organization_id', activeOrganizationId]
			])}`,
			{
				method: 'DELETE',
				headers: {
					...headers,
					'x-user-id': locals.user.id
				}
			}
		);

		const leaveOrgBody = await leaveOrgRes.json();
		if (!leaveOrgRes.ok) {
			logger.error('ORGTEAM_REMOVE_REMOVE', leaveOrgBody);
			return fail(
				leaveOrgRes.status,
				new APIError('Failed to remove user', leaveOrgBody as any).getSerializable()
			);
		} else {
			return leaveOrgBody;
		}
	}
};

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const getInviteEmailBody = (inviterEmail: string, inviteToken: string) => `<html>
	<head>
		<style type="text/css">
			.ExternalClass,.ExternalClass div,.ExternalClass font,.ExternalClass p,.ExternalClass span,.ExternalClass td,img {line-height: 100%;}#outlook a {padding: 0;}.ExternalClass,.ReadMsgBody {width: 100%;}a,blockquote,body,li,p,table,td {-webkit-text-size-adjust: 100%;-ms-text-size-adjust: 100%;}table,td {mso-table-lspace: 0;mso-table-rspace: 0;}img {-ms-interpolation-mode: bicubic;border: 0;height: auto;outline: 0;text-decoration: none;}table {border-collapse: collapse !important;}#bodyCell,#bodyTable,body {height: 100% !important;margin: 0;padding: 0;font-family: ProximaNova, sans-serif;}#bodyCell {padding: 20px;}#bodyTable {width: 600px;}@font-face {font-family: ProximaNova;src: url(https://cdn.auth0.com/fonts/proxima-nova/proximanova-regular-webfont-webfont.eot);src: url(https://cdn.auth0.com/fonts/proxima-nova/proximanova-regular-webfont-webfont.eot?#iefix)format("embedded-opentype"),url(https://cdn.auth0.com/fonts/proxima-nova/proximanova-regular-webfont-webfont.woff) format("woff");font-weight: 400;font-style: normal;}@font-face {font-family: ProximaNova;src: url(https://cdn.auth0.com/fonts/proxima-nova/proximanova-semibold-webfont-webfont.eot);src: url(https://cdn.auth0.com/fonts/proxima-nova/proximanova-semibold-webfont-webfont.eot?#iefix)format("embedded-opentype"),url(https://cdn.auth0.com/fonts/proxima-nova/proximanova-semibold-webfont-webfont.woff) format("woff");font-weight: 600;font-style: normal;}@media only screen and (max-width: 480px) {#bodyTable,body {width: 100% !important;}a,blockquote,body,li,p,table,td {-webkit-text-size-adjust: none !important;}body {min-width: 100% !important;}#bodyTable {max-width: 600px !important;}#signIn {max-width: 280px !important;}}
		</style>
	</head>
	<body>
		<center>
			<table
				style='width: 600px;-webkit-text-size-adjust: 100%;-ms-text-size-adjust: 100%;mso-table-lspace: 0pt;mso-table-rspace: 0pt;margin: 0;padding: 0;font-family: "ProximaNova", sans-serif;border-collapse: collapse !important;height: 100% !important;'
				align="center"
				border="0"
				cellpadding="0"
				cellspacing="0"
				height="100%"
				width="100%"
				id="bodyTable"
			>
				<tr>
					<td
						align="center"
						valign="top"
						id="bodyCell"
						style='-webkit-text-size-adjust: 100%;-ms-text-size-adjust: 100%;mso-table-lspace: 0pt;mso-table-rspace: 0pt;margin: 0;padding: 20px;font-family: "ProximaNova", sans-serif;height: 100% !important;'
					>
						<div class="main">
							<p
								style="text-align: center;-webkit-text-size-adjust: 100%;-ms-text-size-adjust: 100%; margin-bottom: 30px;"
							>
								<img
									src="https://cloud.jamaibase.com/logo.png"
									width="50"
									alt="JamAI Logo"
									style="-ms-interpolation-mode: bicubic;border: 0;height: auto;line-height: 100%;outline: none;text-decoration: none;"
								/>
							</p>

							<h1>${inviterEmail} has invited you to join their organization on JamAI Base</h1>

							<p>You have been invited to join an organization on JamAI Base. Click the link below to accept the invitation:</p>

							<p><a href="${ORIGIN}/join-organization?token=${inviteToken}">Join JamAI Base</a></p>

							<p>This link will expire in 7 days.</p>

							<br />
							Thanks!
							<br />

							<strong>JamAI Base</strong>

							<br /><br />
							<hr style="border: 2px solid #EAEEF3; border-bottom: 0; margin: 20px 0;" />
							<p style="text-align: center;color: #A9B3BC;-webkit-text-size-adjust: 100%;-ms-text-size-adjust: 100%;">
								If you did not make this request, you can ignore this mail.
							</p>
						</div>
					</td>
				</tr>
			</table>
		</center>
	</body>
</html>`;
