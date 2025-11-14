import { PUBLIC_IS_SPA } from '$env/static/public';

//@ts-expect-error missing types
export async function load({ parent }) {
	const data = await parent();

	if (data.ossMode && PUBLIC_IS_SPA === 'true') {
		return {
			activeOrganizationId: 'default',
			dockOpen: true,
			rightDockOpen: true
		};
	}
}
