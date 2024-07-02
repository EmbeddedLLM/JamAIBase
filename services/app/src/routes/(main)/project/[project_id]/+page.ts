import { redirect } from '@sveltejs/kit';

export const load = async ({ params }) => {
	throw redirect(302, `/project/${params.project_id}/action-table`);
};
