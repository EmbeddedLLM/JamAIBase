<script lang="ts">
	import { env as publicEnv } from '$env/dynamic/public';
	import { page } from '$app/state';
	import { browser } from '$app/environment';
	import { activeOrganization, activeProject, loadingProjectData } from '$globalStore';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';

	const { PUBLIC_JAMAI_URL } = publicEnv;

	let { data, children } = $props();
	let { user } = $derived(data);

	const setActiveProject = async () => {
		if (
			browser &&
			page.params.project_id &&
			(page.data.ossMode || $activeOrganization?.id !== $activeProject?.organization_id)
		) {
			$loadingProjectData = { loading: true, error: undefined };

			const projectRes = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/projects?${new URLSearchParams([['project_id', page.params.project_id]])}`
			);
			const projectBody = await projectRes.json();

			if (projectRes.ok) {
				$activeProject = projectBody;
				const matchedOrg = user?.organizations.find(
					(org) => org.id === projectBody?.organization_id
				);
				if (projectBody?.organization_id !== $activeOrganization?.id && matchedOrg) {
					$activeOrganization = matchedOrg;
					activeOrganization.setOrgCookie(matchedOrg.id);
				}
			} else {
				$activeProject = null;
				console.error(projectBody);
				toast.error('Failed to fetch project', {
					id: projectBody?.message || JSON.stringify(projectBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: projectBody?.message || JSON.stringify(projectBody),
						requestID: projectBody?.request_id
					}
				});
				$loadingProjectData = {
					loading: false,
					error: projectBody?.message || JSON.stringify(projectBody)
				};
			}
		}
	};

	$effect(() => {
		page.params.project_id;
		setActiveProject();
	});
</script>

{@render children?.()}
