<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import debounce from 'lodash/debounce';
	import { page } from '$app/stores';
	import { genTableRows, tableState } from '../tablesStore';
	import type { GenTable, GenTableCol } from '$lib/types';

	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { isValidUri } from '$lib/utils';

	export let tableData: GenTable | undefined;
	export let rowThumbs: { [rowID: string]: { [colID: string]: { value: string; url: string } } };

	$: tableData, $genTableRows, debouncedFetchThumbs();
	const debouncedFetchThumbs = debounce(fetchThumbs, 250);
	async function fetchThumbs() {
		if (!tableData || !$genTableRows) return;

		Object.keys(rowThumbs).forEach((key) => {
			if ($genTableRows?.find((row) => row.ID === key) === undefined) {
				delete rowThumbs[key];
			}
		});

		const fileColumns = tableData.cols.filter(
			(col) => col.dtype === 'image' || col.dtype === 'audio'
		);
		if (fileColumns.length === 0) return;

		const rowThumbsArr: string[] = [];
		const rowThumbsMap: typeof $genTableRows = [];
		for (const row of $genTableRows) {
			fileColumns.forEach((col) => {
				if (
					row[col.id]?.value &&
					(rowThumbs[row.ID]?.[col.id] === undefined ||
						row[col.id].value !== rowThumbs[row.ID]?.[col.id]?.value) &&
					!$tableState.streamingRows[row.ID]
				) {
					if (isValidUri(row[col.id].value)) {
						rowThumbsArr.push(row[col.id].value);
					} else {
						// trick validation to return empty string, remove later
						rowThumbsArr.push('s3://placeholder/');
					}

					if (rowThumbsMap.at(-1)?.ID !== row.ID) {
						//@ts-ignore
						rowThumbsMap.push({ ID: row.ID, [col.id]: row[col.id] });
					} else {
						rowThumbsMap[rowThumbsMap.length - 1] = {
							...rowThumbsMap[rowThumbsMap.length - 1],
							[col.id]: row[col.id]
						};
					}
				}
			});
		}

		if (rowThumbsArr.length === 0) return;

		const urlResponse = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/files/url/thumb`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': $page.params.project_id
			},
			body: JSON.stringify({
				uris: rowThumbsArr
			})
		});
		const urlBody = await urlResponse.json();

		if (urlResponse.ok) {
			let cursor = 0;
			let rowIndex = 0;
			(urlBody.urls as string[]).forEach((url) => {
				const relatedFileCols = fileColumns.filter((col) => rowThumbsMap[rowIndex][col.id]);
				skipNullCells(relatedFileCols);

				if (rowThumbs[rowThumbsMap![rowIndex].ID]) {
					rowThumbs[rowThumbsMap![rowIndex].ID][relatedFileCols[cursor].id] = {
						value: rowThumbsMap![rowIndex][relatedFileCols[cursor].id].value,
						url
					};
				} else {
					rowThumbs[rowThumbsMap![rowIndex].ID] = {
						[relatedFileCols[cursor].id]: {
							value: rowThumbsMap![rowIndex][relatedFileCols[cursor].id].value,
							url
						}
					};
				}

				cursor++;
				if (cursor >= relatedFileCols.length) {
					cursor = 0;
					rowIndex++;
				}
			});

			function skipNullCells(relatedFileCols: GenTableCol[]) {
				if (!rowThumbsMap![rowIndex][relatedFileCols[cursor].id].value) {
					cursor++;
					if (cursor >= relatedFileCols.length) {
						cursor = 0;
						rowIndex++;
					}
					skipNullCells(relatedFileCols);
				}
			}
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
</script>
