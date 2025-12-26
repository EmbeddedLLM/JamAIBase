<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import debounce from 'lodash/debounce';
	import { page } from '$app/state';
	import type { Project } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';

	let {
		project,
		projectImgThumb = $bindable()
	}: { project: Project | undefined; projectImgThumb: string } = $props();

	const debouncedFetchThumbs = debounce(fetchThumbs, 250);
	async function fetchThumbs() {
		if (!project?.cover_picture_url) return;

		const urlResponse = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/files/url/thumb`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id ?? ''
			},
			body: JSON.stringify({
				uris: [project?.cover_picture_url]
			})
		});
		const urlBody = await urlResponse.json();

		if (urlResponse.ok) {
			projectImgThumb = urlBody?.urls?.[0] || '';
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
		if (project?.cover_picture_url) {
			debouncedFetchThumbs();
		}
	});
</script>
