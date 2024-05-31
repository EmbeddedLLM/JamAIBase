import { env } from '$env/dynamic/public';
import { error, redirect } from '@sveltejs/kit';

const { PUBLIC_IS_LOCAL } = env;

export function load() {
	if (PUBLIC_IS_LOCAL === 'false') {
		return redirect(302, '/settings/account');
	} else {
		throw error(404, 'Not found');
	}
}
