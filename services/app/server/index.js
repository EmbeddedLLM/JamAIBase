import 'dotenv/config';
import { handler } from '../build/handler.js';
import express from 'express';
import cors from 'cors';
import expressOpenIdConnect from 'express-openid-connect';

const { NODE_ENV, BASE_URL } = process.env;
const FRONTEND_PORT = process.env.FRONTEND_PORT || 4000;

const app = express();
app.use(cors());

if (process.env.PUBLIC_IS_LOCAL === 'false') {
	// The `auth` router attaches /login, /logout and /callback routes to the baseURL
	app.use(
		expressOpenIdConnect.auth({
			authorizationParams: {
				response_type: 'code',
				scope: 'openid profile email offline_access'
			},
			authRequired: false,
			auth0Logout: true,
			baseURL: NODE_ENV === 'production' ? BASE_URL : `http://localhost:${FRONTEND_PORT}`,
			clientID: process.env.AUTH0_CLIENT_ID,
			clientSecret: process.env.AUTH0_CLIENT_SECRET,
			issuerBaseURL: process.env.AUTH0_ISSUER_BASE_URL,
			secret: process.env.AUTH0_SECRET,
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

	app.use(async function (req, res, next) {
		res.locals.user = req.oidc.user;
		let accessToken = req.oidc.accessToken;

		if (accessToken) {
			let { isExpired, refresh } = accessToken;
			if (isExpired()) {
				await refresh();
			}
		}

		next();
	});
}

app.use(handler);

app.listen(FRONTEND_PORT);

console.log('Listening on port:', FRONTEND_PORT);
console.log('http://localhost:' + FRONTEND_PORT);
