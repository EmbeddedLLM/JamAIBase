import { env } from '$env/dynamic/public';
import { error } from '@sveltejs/kit';

const { PUBLIC_IS_LOCAL } = env;

export function load() {
	if (PUBLIC_IS_LOCAL !== 'false') {
		throw error(404, 'Not found');
	}
}
