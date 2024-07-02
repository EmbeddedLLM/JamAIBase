import 'dotenv/config';
import adapter from '@sveltejs/adapter-node';
import adapterStatic from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	// Consult https://kit.svelte.dev/docs/integrations#preprocessors
	// for more information about preprocessors
	preprocess: vitePreprocess(),

	kit: {
		adapter:
			process.env.PUBLIC_IS_SPA === 'true'
				? adapterStatic({
						pages: 'temp',
						assets: 'temp',
						fallback: 'index.html',
						precompress: false,
						strict: true
					})
				: adapter({ out: 'temp' }),
		paths: {
			relative: process.env.PUBLIC_IS_SPA !== 'true'
		},
		alias: {
			$globalStore: 'src/globalStore'
		},
		csrf: {
			checkOrigin: process.env.CHECK_ORIGIN === 'false' ? false : true
		}
	}
};

export default config;
