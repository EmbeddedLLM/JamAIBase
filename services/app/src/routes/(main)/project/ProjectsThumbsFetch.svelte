<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import debounce from 'lodash/debounce';
	import { page } from '$app/state';
	import { isValidUri } from '$lib/utils';
	import type { Project } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';

	let {
		orgProjects,
		projectsThumbs = $bindable()
	}: {
		orgProjects: Project[];
		projectsThumbs: { [projectID: string]: string };
	} = $props();

	const debouncedFetchThumbs = debounce(fetchThumbs, 250);
	async function fetchThumbs() {
		const cacheProjects = $state.snapshot(orgProjects);

		const urlResponse = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/files/url/thumb`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id ?? ''
			},
			body: JSON.stringify({
				uris: cacheProjects.map((proj) =>
					isValidUri(proj.cover_picture_url ?? '') ? proj.cover_picture_url : 's3://placeholder/'
				)
			})
		});
		const urlBody = await urlResponse.json();

		if (urlResponse.ok) {
			projectsThumbs = (urlBody.urls as string[]).reduce(
				(acc, url, index) => {
					acc[cacheProjects[index].id] = url;
					return acc;
				},
				{} as { [projectID: string]: string }
			);
		} else {
			toast.error('Failed to retrieve thumbnails', {
				id: urlBody.message || JSON.stringify(urlBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: urlBody.message || JSON.stringify(urlBody),
					requestID: urlBody.request_id
				}
			});
		}
	}
	$effect(() => {
		if (orgProjects.length) {
			debouncedFetchThumbs();
		}
	});
</script>
