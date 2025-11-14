import { env } from '$env/dynamic/private';
import { CredentialsSignin, SvelteKitAuth, type DefaultSession } from '@auth/sveltekit';

import Credentials from '@auth/sveltekit/providers/credentials';
import logger from './logger';
import type { User } from './types';

const { AUTH_SECRET, OWL_URL, USE_SECURE_COOKIES, IDLE_AUTH_TIMEOUT, ABSOLUTE_AUTH_TIMEOUT } = env;

const DEFAULT_AUTH_ABSOLUTE_TIMEOUT = 86400;
const DEFAULT_AUTH_IDLE_TIMEOUT = 900;

const ABSOLUTE_MAX_LIFETIME =
	(Number(ABSOLUTE_AUTH_TIMEOUT) || DEFAULT_AUTH_ABSOLUTE_TIMEOUT) * 1000;

type SessionUser = Pick<
	User,
	| 'id'
	| 'email'
	| 'name'
	| 'preferred_name'
	| 'preferred_email'
	| 'picture_url'
	| 'preferred_picture_url'
>;

declare module '@auth/sveltekit' {
	interface Session {
		user: SessionUser & DefaultSession['user'];
	}
	interface User extends SessionUser {}
}

class InvalidCredentials extends CredentialsSignin {
	code = 'invalid_credentials';
}
class InsufficientCredentials extends CredentialsSignin {
	code = 'insufficient_credentials';
}
class UserExists extends CredentialsSignin {
	code = 'user_exists';
}
class UserNotFound extends CredentialsSignin {
	code = 'user_not_found';
}

export const { handle } = SvelteKitAuth({
	trustHost: true,
	providers: [
		Credentials({
			id: 'credentials',
			name: 'Credentials',
			credentials: {
				email: {},
				name: {},
				password: {},
				isNewAccount: {}
			},
			authorize: async (credentials) => {
				if (!credentials?.email || !credentials?.password) {
					throw new InsufficientCredentials('Email and password are required');
				}

				if (credentials.isNewAccount === 'true') {
					if (!credentials?.email || !credentials?.name) {
						throw new InsufficientCredentials();
					}
					const response = await fetch(`${OWL_URL}/api/v2/auth/register/password`, {
						method: 'POST',
						headers: {
							'Content-Type': 'application/json'
						},
						body: JSON.stringify({
							email: credentials.email,
							name: credentials.name,
							password: credentials.password
						})
					});

					const data = await response.json();
					if (!response.ok) {
						if (data.error !== 'resource_exists' || data.error !== 'unauthorized') {
							logger.error('AUTH_SIGNUP_ERROR', data);
						}

						if (data.error === 'resource_exists') {
							throw new UserExists(data?.message);
						}
						if (data.error === 'unauthorized') {
							throw new InvalidCredentials(data?.message);
						}
						throw new CredentialsSignin();
					}

					if (data.id) {
						delete data.password_hash;
						return data;
					}
				} else {
					const response = await fetch(`${OWL_URL}/api/v2/auth/login/password`, {
						method: 'POST',
						headers: {
							'Content-Type': 'application/json'
						},
						body: JSON.stringify({
							email: credentials.email,
							password: credentials.password
						})
					});

					const data = await response.json();

					if (!response.ok) {
						if (data.message !== 'User not found.' || data.error !== 'unauthorized') {
							logger.error('AUTH_LOGIN_ERROR', data);
						}

						if (data.message === 'User not found.') {
							throw new UserNotFound(data?.message);
						}
						if (data.error === 'unauthorized') {
							throw new InvalidCredentials(data?.message);
						}
						throw new CredentialsSignin();
					}

					if (data.id) {
						delete data.password_hash;
						return data;
					}
				}

				throw new CredentialsSignin();
			}
		})
	],
	callbacks: {
		// @ts-expect-error ignore
		async session({ session, user, token }) {
			if (token.forceLogout) {
				return null;
			}

			if (user) {
				assignProperties(user, session.user);
			}
			if (token) {
				assignProperties(token, session.user);
			}
			return session;
		},

		async redirect({ url, baseUrl }) {
			// Allows relative callback URLs
			if (url.startsWith('/')) return `${baseUrl}${url}`;
			// Allows callback URLs on the same origin
			return url;
		},

		async jwt({ token, user }) {
			if (user) {
				assignProperties(user, token);
			}

			if (token.createdAt) {
				const age = Date.now() - Number(token.createdAt);
				if (age > ABSOLUTE_MAX_LIFETIME) {
					token.forceLogout = true;
				}
			} else {
				token.createdAt = Date.now();
			}

			return token;
		}
	},
	pages: {
		signIn: '/login',
		newUser: '/register'
	},
	session: {
		strategy: 'jwt'
		// maxAge: Number(IDLE_AUTH_TIMEOUT) || DEFAULT_AUTH_IDLE_TIMEOUT
	},

	secret: AUTH_SECRET,
	useSecureCookies: USE_SECURE_COOKIES === 'true' ? true : undefined
});

function assignProperties(source: Record<string, any>, target: Record<string, any>) {
	const properties = [
		'id',
		'email',
		'name',
		'preferred_name',
		'picture_url',
		'preferred_picture_url'
	];

	properties.forEach((property) => {
		if (source[property] !== undefined) {
			target[property] = source[property];
		}
	});
}
