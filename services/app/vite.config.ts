import { paraglideVitePlugin } from '@inlang/paraglide-js';
import { sveltekit } from '@sveltejs/kit/vite';
import 'dotenv/config';
import express from 'express';
import expressOpenIdConnect from 'express-openid-connect';
import type { ProxyOptions, ViteDevServer } from 'vite';
import devtoolsJson from 'vite-plugin-devtools-json';
import { defineConfig } from 'vitest/config';

const proxy: Record<string, string | ProxyOptions> = {
	'/login': {},
	'/logout': {},
	'/callback': {},
	'/dev-profile': {}
};

function expressPlugin() {
	const app = express();
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
	plugins: [
		devtoolsJson(),
		paraglideVitePlugin({
			project: './project.inlang',
			outdir: './src/lib/paraglide',
			strategy: ['cookie', 'baseLocale']
		}),
		!!process.env.OWL_SERVICE_KEY && !!process.env.AUTH0_CLIENT_SECRET && expressPlugin(),
		sveltekit()
	],
	test: {
		include: ['src/**/*.{test,spec}.{js,ts}']
	}
});
