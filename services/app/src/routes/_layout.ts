import { PUBLIC_IS_LOCAL, PUBLIC_IS_SPA } from '$env/static/public';

//@ts-expect-error missing types
export async function load({ parent }) {
	await parent();

	if (PUBLIC_IS_LOCAL !== 'false' && PUBLIC_IS_SPA === 'true') {
		return {
			activeOrganizationId: 'default',
			dockOpen: true,
			rightDockOpen: true
		};
	}
}
