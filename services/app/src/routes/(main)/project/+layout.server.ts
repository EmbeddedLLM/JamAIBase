import { env } from '$env/dynamic/public';
import { redirect } from '@sveltejs/kit';

const { PUBLIC_IS_LOCAL } = env;

export async function load({ params, parent }) {
	const data = await parent();

	if (PUBLIC_IS_LOCAL === 'false') {
		if (
			params.project_id &&
			!data.organizationData?.projects.find((project) => project.id === params.project_id)
		) {
			throw redirect(302, `/project`);
		}
	}
}
