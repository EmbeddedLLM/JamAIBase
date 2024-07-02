import 'dotenv/config';
import { sveltekit } from '@sveltejs/kit/vite';
import type { ProxyOptions, ViteDevServer } from 'vite';
import express from 'express';
import expressOpenIdConnect from 'express-openid-connect';
import { defineConfig } from 'vitest/config';

const proxy: Record<string, string | ProxyOptions> = {
	'/login': {},
	'/logout': {},
	'/callback': {},
	'/dev-profile': {}
};

function expressPlugin() {
	const app = express();
	if (process.env.PUBLIC_IS_LOCAL === 'false') {
		app.use(
			expressOpenIdConnect.auth({
				authorizationParams: {
					response_type: 'code',
					scope: 'openid profile email offline_access'
				},
				authRequired: false,
				auth0Logout: true,
				baseURL: `http://localhost:5173`,
				clientID: process.env.AUTH0_CLIENT_ID,
				clientSecret: process.env.AUTH0_CLIENT_SECRET,
				issuerBaseURL: process.env.AUTH0_ISSUER_BASE_URL,
				secret: process.env.AUTH0_SECRET,
				attemptSilentLogin: false,
				routes: {
					login: false
				}
			})
		);
		app.get('/login', (req, res) => {
			res.oidc.login({
				returnTo: (typeof req.query.returnTo === 'string' ? req.query.returnTo : '/') || '/'
			});
		});
		app.get('/dev-profile', (req, res) => {
			res.json(req.oidc.user ?? {});
		});
	}

	return {
		name: 'express-plugin',
		config() {
			return {
				server: { proxy },
				preview: { proxy }
			};
		},
		configureServer(server: ViteDevServer) {
			server.middlewares.use(app);
		}
	};
}

export default defineConfig({
	build: {
		target: 'esnext'
	},
	optimizeDeps: {
		esbuildOptions: {
			target: 'esnext'
		}
	},
	plugins: [process.env.PUBLIC_IS_LOCAL === 'false' && expressPlugin(), sveltekit()],
	test: {
		include: ['src/**/*.{test,spec}.{js,ts}']
	}
});
