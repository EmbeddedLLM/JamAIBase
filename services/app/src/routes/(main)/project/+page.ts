import { PUBLIC_IS_LOCAL } from '$env/static/public';
import { redirect } from '@sveltejs/kit';

export function load() {
	if (PUBLIC_IS_LOCAL !== 'false') {
		throw redirect(302, '/project/default');
	}
}
