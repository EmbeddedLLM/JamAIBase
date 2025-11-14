import { env } from '$env/dynamic/private';
import { emailCodeCooldownSecs } from '$lib/constants.js';
import logger, { APIError } from '$lib/logger.js';
import { error, fail, redirect } from '@sveltejs/kit';
import { ManagementClient } from 'auth0';

const {
	AUTH0_CLIENT_ID,
	AUTH0_ISSUER_BASE_URL,
	AUTH0_MGMTAPI_CLIENT_ID,
	AUTH0_MGMTAPI_CLIENT_SECRET,
	ORIGIN,
	OWL_SERVICE_KEY,
	OWL_URL,
	RESEND_API_KEY
} = env;

const management = new ManagementClient({
	domain: AUTH0_ISSUER_BASE_URL?.replace('https://', '') ?? '',
	clientId: AUTH0_MGMTAPI_CLIENT_ID ?? '',
	clientSecret: AUTH0_MGMTAPI_CLIENT_SECRET ?? ''
});

const headers = {
	Authorization: `Bearer ${OWL_SERVICE_KEY}`
};

export async function load({ locals, url }) {
	if (!locals.user || locals.user.email_verified) {
		throw redirect(302, '/');
	}

	const token = url.searchParams.get('token');

	if (token) {
		const verifyUserRes = await fetch(
			`${OWL_URL}/api/v2/users/verify/email?${new URLSearchParams([['verification_code', token]])}`,
			{
				method: 'POST',
				headers: {
					...headers,
					'x-user-id': locals.user.id ?? ''
				}
			}
		);

		const verifyUserBody = await verifyUserRes.json();
		if (!verifyUserRes.ok) {
			if (verifyUserRes.status !== 404) {
				logger.error('VERIFYEMAIL_LOAD_TOKEN', verifyUserBody);
			}
			throw error(verifyUserRes.status, verifyUserBody.message || JSON.stringify(verifyUserBody));
		} else {
			throw redirect(302, '/');
		}
	}

	const listCodesRes = await fetch(
		`${OWL_URL}/api/v2/users/verify/email/code/list?${new URLSearchParams([
			['limit', '1'],
			['search_query', locals.user.email],
			['search_columns', 'user_email']
		])}`,
		{
			headers: {
				...headers,
				'x-user-id': '0'
			}
		}
	);
	const listCodesBody = await listCodesRes.json();

	if (
		listCodesRes.ok &&
		(!listCodesBody.items[0] ||
			new Date(listCodesBody.items[0]?.expiry).getTime() < new Date().getTime())
	) {
		const sendCodeRes = await fetch(
			`${OWL_URL}/api/v2/users/verify/email/code?${new URLSearchParams([
				['user_email', locals.user.email],
				['valid_days', '1']
			])}`,
			{
				method: 'POST',
				headers: {
					...headers,
					'x-user-id': '0'
				}
			}
		);
		const sendCodeBody = await sendCodeRes.json();

		if (!sendCodeRes.ok) {
			logger.error('VERIFYEMAIL_LOAD_GETCODE', sendCodeBody);
		} else {
			const sendEmailRes = await fetch('https://api.resend.com/emails', {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${RESEND_API_KEY}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					from: 'JamAI Base <no-reply@jamaibase.com>',
					to: locals.user.email,
					subject: 'Verify your JamAI Base email address',
					html: getVerificationEmailBody(sendCodeBody.id)
				})
			});

			if (!sendEmailRes.ok) {
				logger.error('VERIFYEMAIL_LOAD_SENDCODE', await sendEmailRes.json());
			}
		}
	}
}

export const actions = {
	'resend-verification-email': async ({ locals }) => {
		//* Verify user perms
		if (!locals.user) {
			return fail(401, new APIError('Unauthorized').getSerializable());
		}

		if (locals.auth0Mode) {
			try {
				const resendEmailRes = await management.jobs.verifyEmail({
					user_id: locals.user.sub!,
					client_id: AUTH0_CLIENT_ID
				});
				if (resendEmailRes.status !== 200 && resendEmailRes.status !== 201) {
					logger.error('VERIFY_RESEND_EMAIL', resendEmailRes.data);
					return fail(
						resendEmailRes.status,
						new APIError(
							'Failed to resend verification email',
							resendEmailRes.data as any
						).getSerializable()
					);
				} else {
					return resendEmailRes.data;
				}
			} catch (err) {
				logger.error('VERIFY_RESEND_EMAILERR', err);
				return fail(
					500,
					new APIError('Failed to resend verification email', err as any).getSerializable()
				);
			}
		} else {
			try {
				//? Check if resend cooldown is up
				const response = await fetch(
					`${OWL_URL}/api/v2/users/verify/email/code/list?${new URLSearchParams([
						['limit', '1'],
						['search_query', locals.user!.email],
						['search_columns', 'user_email']
					])}`,
					{
						headers: {
							...headers,
							'x-user-id': '0'
						}
					}
				);
				const responseBody = await response.json();

				if (response.ok) {
					if (
						new Date().getTime() - new Date(responseBody.items[0]?.created_at).getTime() >
						emailCodeCooldownSecs * 1000
					) {
						const sendCodeRes = await fetch(
							`${OWL_URL}/api/v2/users/verify/email/code?${new URLSearchParams([
								['user_email', locals.user.email],
								['valid_days', '1']
							])}`,
							{
								method: 'POST',
								headers: {
									...headers,
									'x-user-id': '0'
								}
							}
						);
						const sendCodeBody = await sendCodeRes.json();

						if (!sendCodeRes.ok) {
							logger.error('VERIFYEMAIL_RESEND_GETCODE', sendCodeBody);
						} else {
							const sendEmailRes = await fetch('https://api.resend.com/emails', {
								method: 'POST',
								headers: {
									Authorization: `Bearer ${RESEND_API_KEY}`,
									'Content-Type': 'application/json'
								},
								body: JSON.stringify({
									from: 'JamAI Base <no-reply@jamaibase.com>',
									to: locals.user.email,
									subject: 'Verify your JamAI Base email address',
									html: getVerificationEmailBody(sendCodeBody.id)
								})
							});

							if (!sendEmailRes.ok) {
								logger.error('VERIFYEMAIL_RESEND_SENDCODE', await sendEmailRes.json());
							}
						}
					} else {
						return fail(
							403,
							new APIError(
								'Too many resend verification email requests, please wait.'
							).getSerializable()
						);
					}
				} else {
					logger.error('VERIFY_RESEND_LISTCODE', responseBody);
					return fail(
						500,
						new APIError('Failed to resend verification email', responseBody).getSerializable()
					);
				}
			} catch (err) {
				logger.error('VERIFY_RESEND_EMAILERR', err);
				return fail(
					500,
					new APIError('Failed to resend verification email', err as any).getSerializable()
				);
			}
		}
	}
};

const getVerificationEmailBody = (verificationToken: string) => `<html>
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
              <h1>Verify your email address</h1>
              <p>Welcome to JamAI Base! To complete your account setup, please verify your email address by clicking the link below:</p>
              <table border="0" cellspacing="0" cellpadding="0" style="margin: 20px 0;">
                <tr>
                  <td align="center" style="background-color: #007bff; padding: 12px 24px; border-radius: 4px;">
                    <a href="${ORIGIN}/verify-email?token=${verificationToken}" 
                       style="color: #ffffff; text-decoration: none; font-weight: 600; font-size: 16px; display: inline-block;"
                       target="_blank">
                      Verify Email Address
                    </a>
                  </td>
                </tr>
              </table>
              <p>If the button above doesn't work, you can copy and paste this link into your browser:</p>
              <p style="word-break: break-all; color: #666; font-size: 14px;">${ORIGIN}/verify-email?token=${verificationToken}</p>
              <p>This verification link will expire in 24 hours.</p>
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
