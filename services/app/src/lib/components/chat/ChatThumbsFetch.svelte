<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import debounce from 'lodash/debounce';
	import { page } from '$app/state';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';

	let {
		uris,
		rowThumbs = $bindable()
	}: {
		uris: { [rowID: string]: { [colID: string]: string } };
		rowThumbs: { [uri: string]: string };
	} = $props();

	const debouncedFetchThumbs = debounce(fetchThumbs, 250);
	async function fetchThumbs() {
		Object.values(uris).forEach((cols) =>
			Object.values(cols).forEach((uri) => (rowThumbs[uri] = rowThumbs[uri] ?? ''))
		);

		const rowThumbsUris = Object.keys(rowThumbs);
		const urlResponse = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/files/url/thumb`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id
			},
			body: JSON.stringify({
				uris: rowThumbsUris
			})
		});
		const urlBody = await urlResponse.json();

		if (urlResponse.ok) {
			(urlBody.urls as string[]).forEach((url, index) => {
				const uri = rowThumbsUris[index];
				rowThumbs[uri] = url;
			});
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

		rowThumbs = rowThumbs;
	}
	$effect(() => {
		uris;
		debouncedFetchThumbs();
	});
</script>
