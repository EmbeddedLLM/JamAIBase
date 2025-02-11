<script lang="ts">
	import { PUBLIC_IS_LOCAL, PUBLIC_JAMAI_URL } from '$env/static/public';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import { activeOrganization, activeProject, loadingProjectData } from '$globalStore';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';

	export let data;
	$: ({ userData } = data);

	//@ts-ignore
	$: $page.params.project_id, setActiveProject();
	const setActiveProject = async () => {
		if (
			browser &&
			$page.params.project_id &&
			(PUBLIC_IS_LOCAL !== 'false' ||
				$activeOrganization?.organization_id !== $activeProject?.organization_id)
		) {
			$loadingProjectData = { loading: true, error: undefined };

			const projectRes = await fetch(
				`${PUBLIC_JAMAI_URL}/api/admin/org/v1/projects/${$page.params.project_id}`
			);
			const projectBody = await projectRes.json();

			if (projectRes.ok) {
				$activeProject = projectBody;
				const matchedOrg = userData?.member_of.find(
					(org) => org.organization_id === projectBody?.organization_id
				);
				if (projectBody?.organization_id !== $activeOrganization?.organization_id && matchedOrg) {
					$activeOrganization = matchedOrg;
				}
			} else {
				$activeProject = null;
				console.error(projectBody);
				toast.error('Failed to fetch project', {
					id: projectBody?.err_message?.message || JSON.stringify(projectBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: projectBody?.err_message?.message || JSON.stringify(projectBody),
						requestID: projectBody?.err_message?.request_id
					}
				});
				$loadingProjectData = {
					loading: false,
					error: projectBody?.err_message?.message || JSON.stringify(projectBody)
				};
			}
		}
	};
</script>

<slot />
