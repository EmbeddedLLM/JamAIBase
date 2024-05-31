<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { onMount } from 'svelte';
	import { invalidate } from '$app/navigation';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import GripVertical from 'lucide-svelte/icons/grip-vertical';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import Dropzone from 'svelte-file-dropzone/Dropzone.svelte';
	import { showRightDock, uploadQueue } from '$globalStore';
	import logger from '$lib/logger';
	import type {
		ActionTable,
		ActionTableCol,
		ActionTableRow,
		GenTableStreamEvent
	} from '$lib/types';

	import BreadcrumbsBar from '../../../../BreadcrumbsBar.svelte';
	import KnowledgeTables from './KnowledgeTables.svelte';
	import {
		AddColumnDialog,
		AddRowDialog,
		AddTableDialog,
		DeleteDialogs,
		UploadingFileDialog
	} from './(dialogs)';
	import ColumnSettings from './ColumnSettings.svelte';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import * as Pagination from '$lib/components/ui/pagination';
	import { Button } from '$lib/components/ui/button';
	import Checkbox from '$lib/components/Checkbox.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import NoRowsGraphic from './NoRowsGraphic.svelte';
	import DblArrowRightIcon from '$lib/icons/DblArrowRightIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';
	import RowIcon from '$lib/icons/RowIcon.svelte';
	import TuneIcon from '$lib/icons/TuneIcon.svelte';
	import ArrowLeftIcon from '$lib/icons/ArrowLeftIcon.svelte';
	import ArrowRightIcon from '$lib/icons/ArrowRightIcon.svelte';
	import MoreVertIcon from '$lib/icons/MoreVertIcon.svelte';
	import ArrowFilledRightIcon from '$lib/icons/ArrowFilledRightIcon.svelte';
	import ColumnIcon from '$lib/icons/ColumnIcon.svelte';
	import RegenerateIcon from '$lib/icons/RegenerateIcon.svelte';

	const { PUBLIC_JAMAI_URL } = env;

	const RESTRICTED_COLUMNS = ['ID', 'Updated at'];
	const EMBED_COLUMNS = ['Title Embed', 'Text Embed'];

	export let data;
	$: ({ table } = data);
	$: tableData = structuredClone(table?.tableData); // Client reorder column
	$: rows = structuredClone(table?.rows); // Client edit row
	let streamingRows: { [key: string]: boolean } = {};

	let isUploadingFile = false;

	let rightDockButton: HTMLButtonElement;
	let showRightDockButton = false;

	//TODO: Change in prod
	let selected: string[] = [];
	let shiftOrigin: number | null = null;

	let isAddingTable = false;
	let isAddingColumn: { type: 'input' | 'output'; showDialog: boolean } = {
		type: 'input',
		showDialog: false
	};
	let isAddingRow = false;
	let isLoadingAddRow = false; //? Add row loading
	let isDeletingTable: string | null = null;
	let isDeletingColumn: string | null = null;
	let isDeletingRow: string[] | null = null;
	let isColumnSettingsOpen: { column: ActionTableCol | null; showMenu: boolean } = {
		column: null,
		showMenu: false
	};

	//? Reorder columns
	let isReorderLoading = false;
	let dragMouseCoords: {
		x: number;
		y: number;
		startX: number;
		startY: number;
		width: number;
	} | null = null;
	let draggingColumn: ActionTable['cols'][number] | null = null;
	let draggingColumnIndex: number | null = null;
	let hoveredColumnIndex: number | null = null;

	let isEditingCell: { rowID: string; columnID: string } | null = null;

	$: count = table?.total_rows ?? 0;
	$: perPage = 20;
	$: currentPage = parseInt($page.url.searchParams.get('page') ?? '1');

	$: resetOnUpdate(data.table?.tableData);
	function resetOnUpdate(tableData: ActionTable | undefined) {
		selected = [];
		isColumnSettingsOpen = { column: null, showMenu: false };
	}

	function refetchTable() {
		//? Don't refetch while streaming
		if (Object.keys(streamingRows).length === 0) {
			invalidate('knowledge-table:slug');
		}
	}

	function mouseMoveListener(e: MouseEvent) {
		const tableArea = document.getElementById('knowledge-table');
		const el = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement;

		//* Show/hide the right dock button on hover right side
		if (
			rightDockButton.contains(el) ||
			(tableArea?.contains(el) && tableArea?.offsetWidth - (e.clientX - tableArea?.offsetLeft) < 75)
		) {
			showRightDockButton = true;
		} else {
			showRightDockButton = false;
		}
	}

	$: if (
		tableData &&
		draggingColumnIndex != null &&
		hoveredColumnIndex != null &&
		draggingColumnIndex != hoveredColumnIndex
	) {
		[tableData.cols[draggingColumnIndex], tableData.cols[hoveredColumnIndex]] = [
			tableData.cols[hoveredColumnIndex],
			tableData.cols[draggingColumnIndex]
		];

		draggingColumnIndex = hoveredColumnIndex;
	}

	async function handleSaveOrder() {
		if (!tableData) return;
		if (isReorderLoading) return;
		isReorderLoading = true;

		const response = await fetch(`/api/v1/gen_tables/knowledge/columns/reorder`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				table_id: tableData.id,
				column_names: tableData.cols.flatMap(({ id }) =>
					id === 'ID' || id === 'Updated at' ? [] : id
				)
			})
		});

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('KNOWTBL_TBL_REORDER', responseBody);
			alert('Failed to reorder columns: ' + (responseBody.message || JSON.stringify(responseBody)));
			tableData = table?.tableData;
		} else {
			refetchTable();
		}

		isReorderLoading = false;
	}

	async function handleSaveEdit(
		e: KeyboardEvent & {
			currentTarget: EventTarget & HTMLTextAreaElement;
		}
	) {
		if (!tableData || !isEditingCell || !rows) return;
		const originalValue = rows.find((row) => row.ID === isEditingCell!.rowID)?.[
			isEditingCell.columnID
		];
		const editedValue = e.currentTarget.value;
		const cellToUpdate = isEditingCell;

		//? Optimistic update
		rows = rows.map((row) => {
			if (row.ID === cellToUpdate.rowID) {
				return {
					...row,
					[cellToUpdate.columnID]: { value: editedValue }
				};
			}
			return row;
		});

		const response = await fetch(`/api/v1/gen_tables/knowledge/rows/update`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				table_id: tableData.id,
				row_id: cellToUpdate.rowID,
				data: {
					[cellToUpdate.columnID]: editedValue
				}
			})
		});

		if (!response.ok) {
			const responseBody = await response.json();
			logger.error('KNOWTBL_TBL_ROWEDIT', responseBody);
			alert('Failed to edit row: ' + (responseBody.message || JSON.stringify(responseBody)));

			//? Revert back to original value
			rows = rows.map((row) => {
				if (row.ID === cellToUpdate.rowID) {
					return {
						...row,
						[cellToUpdate.columnID]: {
							value: originalValue
						}
					};
				}
				return row;
			});
		} else {
			isEditingCell = null;
			refetchTable();
		}
	}

	//? Select row
	function handleSelectRow(
		e: CustomEvent<{ event: MouseEvent; value: boolean }>,
		row: ActionTableRow
	) {
		if (!rows) return;
		//? Select multiple rows with shift key
		const rowIndex = rows.findIndex(({ ID }) => ID === row.ID);
		if (e.detail.event.shiftKey && selected.length && shiftOrigin != null) {
			if (shiftOrigin < rowIndex) {
				selected = [
					...selected.filter((i) => !rows?.some(({ ID }) => ID === i)),
					...rows.slice(shiftOrigin, rowIndex + 1).map(({ ID }) => ID)
				];
			} else if (shiftOrigin > rowIndex) {
				selected = [
					...selected.filter((i) => !rows?.some(({ ID }) => ID === i)),
					...rows.slice(rowIndex, shiftOrigin + 1).map(({ ID }) => ID)
				];
			} else {
				selectOne();
			}
		} else {
			selectOne();
			shiftOrigin = rowIndex;
		}

		function selectOne() {
			if (selected.find((i) => i === row.ID)) {
				selected = selected.filter((i) => i !== row.ID);
			} else {
				selected = [...selected, row.ID];
			}
		}
	}

	async function handleRegenRow(toRegenRowIds: string[]) {
		if (!rows) return;

		streamingRows = {
			...streamingRows,
			...toRegenRowIds.reduce((acc, curr) => ({ ...acc, [curr]: true }), {})
		};

		//? Optimistic update, clear row
		const originalValues = toRegenRowIds.map((toRegenRowId) => ({
			id: toRegenRowId,
			value: rows!.find((row) => row.ID === toRegenRowId)!
		}));
		rows = rows?.map((row) => {
			if (toRegenRowIds.includes(row.ID)) {
				return {
					...row,
					...Object.fromEntries(
						Object.entries(row).map(([key, value]) => {
							if (key === 'ID' || key === 'Updated at') {
								return [key, value as string];
							} else {
								return [
									key,
									{
										value: tableData?.cols.find((col) => col.id == key)?.gen_config
											? ''
											: (value as { value: any }).value
									}
								];
							}
						})
					)
				};
			}
			return row;
		});

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge/rows/regen`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				table_id: $page.params.table_id,
				row_ids: toRegenRowIds,
				stream: true
			})
		});

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error('KNOWTBL_ROW_REGEN', responseBody);
			alert('Failed to regenerate row: ' + (responseBody.message || JSON.stringify(responseBody)));

			//? Revert back to original value
			rows = rows.map((row) => {
				const originalValue = originalValues.find((i) => i.id === row.ID);
				if (toRegenRowIds.includes(row.ID) && originalValue) {
					return originalValue.value;
				}
				return row;
			});
		} else {
			//Delete all data except for inputs
			rows = rows.map((row) => {
				if (toRegenRowIds.includes(row.ID)) {
					return {
						...row,
						...Object.fromEntries(
							Object.entries(row).map(([key, value]) => {
								if (key === 'ID' || key === 'Updated at') {
									return [key, value as string];
								} else {
									return [
										key,
										{
											value: tableData?.cols.find((col) => col.id == key)?.gen_config
												? ''
												: (value as { value: any }).value
										}
									];
								}
							})
						)
					};
				}
				return row;
			});

			const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();

			let isStreaming = true;
			let lastMessage = '';
			while (isStreaming) {
				try {
					const { value, done } = await reader.read();
					if (done) break;

					if (value.endsWith('\n\n')) {
						const lines = (lastMessage + value)
							.split('\n\n')
							.filter((i) => i.trim())
							.flatMap((line) => line.split('\n')); //? Split by \n to handle collation

						lastMessage = '';

						for (const line of lines) {
							const sumValue = line.replace(/^data: /, '').replace(/data: \[DONE\]\s+$/, '');

							if (sumValue.trim() == '[DONE]') break;

							let parsedValue;
							try {
								parsedValue = JSON.parse(sumValue) as GenTableStreamEvent;
							} catch (err) {
								console.error('Error parsing:', sumValue);
								logger.error('KNOWTBL_ROW_REGENSTREAMPARSE', {
									parsing: sumValue,
									error: err
								});
								continue;
							}

							if (parsedValue.object == 'gen_table.completion.chunk') {
								//* Add chunk to active row
								//@ts-expect-error wtf
								const rowMatchIndex = rows.findIndex((row) => row.ID == parsedValue.row_id);
								if (rowMatchIndex != undefined && rowMatchIndex != -1) {
									//@ts-expect-error wtf
									const [start, end] = [
										rows?.slice(0, rowMatchIndex),
										rows?.slice(rowMatchIndex + 1)
									];
									rows = [
										...(start ?? []),
										{
											...rows![rowMatchIndex],
											[parsedValue.output_column_name]: {
												value:
													(rows![rowMatchIndex][parsedValue.output_column_name]?.value ?? '') +
													(parsedValue.choices[0].message.content ?? '')
											}
										},
										...(end ?? [])
									];
								}
							} else {
								console.log('Unknown message:', parsedValue);
							}
						}
					} else {
						lastMessage += value;
					}
				} catch (err) {
					// logger.error('ACTIONTBL_ROW_REGENSTREAM', err);
					console.error(err);

					//? Below necessary for retry
					for (const toRegenRowId of toRegenRowIds) {
						delete streamingRows[toRegenRowId];
					}
					streamingRows = streamingRows;

					refetchTable();

					throw err;
				}
			}

			refetchTable();
		}

		for (const toRegenRowId of toRegenRowIds) {
			delete streamingRows[toRegenRowId];
		}
		streamingRows = streamingRows;

		refetchTable();
	}

	async function addRowFunction(data: any) {
		isLoadingAddRow = true;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/knowledge/rows/add`, {
			method: 'POST',
			headers: {
				Accept: 'text/event-stream',
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				table_id: $page.params.table_id,
				data: [data],
				stream: true
			})
		});

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error('KNOWTBL_ROW_ADD', responseBody);
			alert('Failed to add row: ' + (responseBody.message || JSON.stringify(responseBody)));
		} else {
			isAddingRow = false;
			isLoadingAddRow = false;

			const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();

			let isStreaming = true;
			let lastMessage = '';
			let rowId = '';
			let addedRow = false;
			while (isStreaming) {
				try {
					const { value, done } = await reader.read();
					if (done) break;

					if (value.endsWith('\n\n')) {
						const lines = (lastMessage + value)
							.split('\n\n')
							.filter((i) => i.trim())
							.flatMap((line) => line.split('\n')); //? Split by \n to handle collation

						lastMessage = '';

						for (const line of lines) {
							const sumValue = line.replace(/^data: /, '').replace(/data: \[DONE\]\s+$/, '');

							if (sumValue.trim() == '[DONE]') break;

							let parsedValue;
							try {
								parsedValue = JSON.parse(sumValue) as GenTableStreamEvent;
							} catch (err) {
								console.error('Error parsing:', sumValue);
								logger.error('KNOWTBL_ROW_ADDSTREAMPARSE', { parsing: sumValue, error: err });
								continue;
							}

							if (parsedValue.object == 'gen_table.completion.chunk') {
								rowId = parsedValue.row_id;
								streamingRows = {
									...streamingRows,
									[parsedValue.row_id]: true
								};

								//* Add chunk to active row
								if (!addedRow) {
									rows = [
										{
											...(Object.fromEntries(
												Object.entries(data).map(([key, value]) => [
													key,
													{ value: value as string }
												])
											) as any),
											ID: parsedValue.row_id,
											'Updated at': new Date().toISOString(),
											[parsedValue.output_column_name]: {
												value: parsedValue.choices[0].message.content ?? ''
											}
										},
										...(rows ?? [])
									];
									addedRow = true;
								} else {
									const rowMatchIndex = rows?.findIndex((row) => row.ID == parsedValue.row_id);

									if (rowMatchIndex != undefined && rowMatchIndex != -1) {
										const [start, end] = [
											rows?.slice(0, rowMatchIndex),
											rows?.slice(rowMatchIndex + 1)
										];
										rows = [
											...(start ?? []),
											{
												...rows![rowMatchIndex],
												[parsedValue.output_column_name]: {
													value:
														(rows![rowMatchIndex][parsedValue.output_column_name]?.value ?? '') +
														(parsedValue.choices[0].message.content ?? '')
												}
											},
											...(end ?? [])
										];
									}
								}
							} else {
								console.log('Unknown message:', parsedValue);
							}
						}
					} else {
						lastMessage += value;
					}
				} catch (err) {
					logger.error('KNOWTBL_ROW_ADDSTREAM', err);
					console.error(err);
					break;
				}
			}

			delete streamingRows[rowId];
			streamingRows = streamingRows;

			refetchTable();
		}
	}

	function handleUploadClick() {
		(document.querySelector('.dropzone > input[type="file"]') as HTMLElement).click();
	}

	async function handleFilesSelectUpload(e: CustomEvent<any>) {
		const { acceptedFiles, fileRejections } = e.detail;
		const acceptedFilesWithPath = (acceptedFiles as any[]).map((file: File) => ({
			file,
			uploadTo: 'knowledge-table',
			table_id: $page.params.table_id
		}));

		//? Show then hide graphic
		isUploadingFile = true;
		setTimeout(() => (isUploadingFile = false), 3000);

		$uploadQueue.queue = [...$uploadQueue.queue, ...acceptedFilesWithPath];
		$uploadQueue = $uploadQueue;

		if (fileRejections.length) {
			if (
				fileRejections.some((file: any) =>
					file.errors.some((error: any) => error.code == 'file-invalid-type')
				)
			) {
				alert('Files must be of type: pdf, doc, docx, ppt, pptx, xls, xlsx, csv, md, txt');
			} else {
				alert('Some files were rejected');
			}
		}
	}

	//! Listen to state update
	$: if (typeof $uploadQueue.queue.length === 'number' && browser) {
		// FIXME: Table wont refetch if rows are streaming while uploading
		refetchTable();
	}

	function keyboardNavigate(e: KeyboardEvent) {
		if (!rows) return;
		const isCtrl = window.navigator.userAgent.indexOf('Mac') != -1 ? e.metaKey : e.ctrlKey;
		const activeElement = document.activeElement as HTMLElement;
		const isInputActive = activeElement.tagName == 'INPUT' || activeElement.tagName == 'TEXTAREA';
		if (isCtrl && e.key === 'a' && !isInputActive) {
			e.preventDefault();
			selected = [
				...selected.filter((i) => !rows?.some(({ ID }) => ID === i)),
				...rows.map(({ ID }) => ID)
			];
		}
	}
</script>

<svelte:window on:mousemove={mouseMoveListener} />
<svelte:document on:keydown={keyboardNavigate} />

<svelte:head>
	<title>{$page.params.table_id} - Knowledge Table</title>
</svelte:head>

<div
	style={`grid-template-columns: minmax(0, auto) ${$showRightDock ? '20rem' : '0rem'};`}
	class="grid h-screen transition-[grid-template-columns] duration-300 bg-[#FAFBFC] data-dark:bg-[#1E2024]"
>
	<section
		id="knowledge-table"
		class="relative flex flex-col pt-0 pb-12 min-h-0 max-h-screen min-w-0 overflow-hidden"
	>
		<Dropzone
			on:drop={handleFilesSelectUpload}
			multiple={true}
			accept={['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.csv', '.md', '.txt']}
			inputElement={undefined}
			containerClasses="max-h-[0] !p-0 !border-none overflow-hidden"
		/>

		<BreadcrumbsBar />

		<div
			inert={isColumnSettingsOpen.showMenu}
			class="flex items-center justify-between px-4 py-3 gap-2"
		>
			<div class="flex items-center gap-2">
				<RowIcon class="flex-[0_0_auto] h-6 w-6 text-secondary" />
				<span class="font-medium line-clamp-1">
					{tableData ? tableData.id : table?.error == 404 ? 'Not found' : 'Failed to load'}
				</span>
			</div>

			<div class="flex items-center gap-1.5">
				{#if tableData && rows}
					<div class="flex items-center gap-4">
						<Button
							on:click={handleUploadClick}
							class="flex items-center gap-2 px-2.5 py-0 h-9 text-text bg-black/[0.04] data-dark:bg-white/[0.06] hover:bg-black/[0.1] data-dark:hover:bg-white/[0.1]"
						>
							<svg
								viewBox="0 0 18 18"
								fill="none"
								xmlns="http://www.w3.org/2000/svg"
								class="h-5 aspect-square"
							>
								<path
									d="M11.2502 3.375C10.1328 3.37492 9.04067 3.70752 8.11303 4.33043C7.18538 4.95333 6.46421 5.83833 6.0414 6.87263C5.50039 6.73435 4.93615 6.71274 4.38614 6.80921C3.83614 6.90568 3.31294 7.11804 2.85128 7.43218C2.38962 7.74632 2.00006 8.15507 1.70845 8.63128C1.41684 9.1075 1.22986 9.64029 1.15992 10.1943C1.08997 10.7483 1.13867 11.3109 1.30276 11.8446C1.46686 12.3784 1.74261 12.8711 2.1117 13.2901C2.4808 13.7092 2.9348 14.0449 3.44357 14.275C3.95235 14.5052 4.50425 14.6245 5.06265 14.625H5.62515C5.77434 14.625 5.91741 14.5657 6.0229 14.4602C6.12839 14.3548 6.18765 14.2117 6.18765 14.0625C6.18765 13.9133 6.12839 13.7702 6.0229 13.6648C5.91741 13.5593 5.77434 13.5 5.62515 13.5H5.06265C4.6457 13.4996 4.23405 13.4066 3.85749 13.2275C3.48094 13.0485 3.1489 12.788 2.88541 12.4648C2.62192 12.1417 2.43357 11.764 2.33401 11.3591C2.23444 10.9542 2.22614 10.5323 2.30971 10.1238C2.39328 9.7153 2.56663 9.3305 2.81721 8.99724C3.06779 8.66399 3.38933 8.39062 3.75855 8.19692C4.12778 8.00322 4.53545 7.89404 4.95207 7.87727C5.36868 7.86051 5.78381 7.93659 6.1674 8.1C6.24061 8.13136 6.31963 8.14682 6.39926 8.14535C6.47888 8.14388 6.55728 8.12553 6.62928 8.0915C6.70128 8.05746 6.76523 8.00853 6.8169 7.94794C6.86858 7.88734 6.90679 7.81647 6.92903 7.74C7.13196 7.04517 7.49951 6.40955 8.0005 5.88707C8.50148 5.36459 9.12112 4.97068 9.80682 4.73876C10.4925 4.50684 11.224 4.44376 11.9393 4.55487C12.6546 4.66599 13.3325 4.94801 13.9156 5.37701C14.4986 5.80601 14.9695 6.36933 15.2884 7.01917C15.6073 7.669 15.7647 8.38617 15.7473 9.10982C15.7299 9.83347 15.5381 10.5422 15.1884 11.176C14.8386 11.8097 14.3411 12.3497 13.7381 12.7502C13.6766 12.7911 13.6237 12.8437 13.5825 12.905C13.5413 12.9663 13.5126 13.0352 13.498 13.1076C13.4834 13.18 13.4832 13.2546 13.4974 13.3271C13.5116 13.3996 13.54 13.4686 13.5809 13.5301C13.6218 13.5916 13.6744 13.6445 13.7357 13.6857C13.797 13.7269 13.8658 13.7556 13.9383 13.7702C14.0107 13.7848 14.0853 13.785 14.1578 13.7708C14.2303 13.7566 14.2992 13.7282 14.3608 13.6873C15.1343 13.1744 15.7688 12.4778 16.2076 11.6599C16.6463 10.842 16.8757 9.92816 16.8752 9C16.8752 5.89331 14.3568 3.375 11.2502 3.375Z"
									fill="currentColor"
								/>
								<path
									d="M10.2696 10.32C10.2168 10.2588 10.1514 10.2097 10.0779 10.1761C10.0045 10.1424 9.9246 10.125 9.84378 10.125C9.76297 10.125 9.6831 10.1424 9.60962 10.1761C9.53614 10.2097 9.47077 10.2588 9.41797 10.32L7.44922 12.5998C7.40095 12.6557 7.36416 12.7206 7.34096 12.7907C7.31776 12.8608 7.3086 12.9349 7.31401 13.0085C7.31941 13.0822 7.33928 13.1541 7.37247 13.2201C7.40566 13.2861 7.45152 13.3449 7.50744 13.3932C7.56336 13.4414 7.62824 13.4782 7.69837 13.5014C7.76851 13.5246 7.84252 13.5338 7.9162 13.5284C7.98987 13.523 8.06176 13.5031 8.12776 13.4699C8.19376 13.4367 8.25257 13.3909 8.30084 13.335L9.28128 12.1998V15.1878C9.28128 15.337 9.34054 15.4801 9.44603 15.5856C9.55152 15.6911 9.6946 15.7503 9.84378 15.7503C9.99297 15.7503 10.136 15.6911 10.2415 15.5856C10.347 15.4801 10.4063 15.337 10.4063 15.1878V12.1998L11.3867 13.335C11.435 13.3909 11.4938 13.4367 11.5598 13.4699C11.6258 13.5031 11.6977 13.523 11.7714 13.5284C11.845 13.5338 11.9191 13.5246 11.9892 13.5014C12.0593 13.4782 12.1242 13.4414 12.1801 13.3932C12.236 13.3449 12.2819 13.2861 12.3151 13.2201C12.3483 13.1541 12.3681 13.0822 12.3736 13.0085C12.379 12.9349 12.3698 12.8608 12.3466 12.7907C12.3234 12.7206 12.2866 12.6557 12.2383 12.5998L10.2696 10.32Z"
									fill="currentColor"
								/>
							</svg>

							Upload
						</Button>
					</div>

					<DropdownMenu.Root>
						<DropdownMenu.Trigger asChild let:builder>
							<Button
								builders={[builder]}
								variant="ghost"
								class="flex gap-3 p-0 px-2 h-9 rounded-md border border-[#E5E5E5] data-dark:border-[#666] bg-white data-dark:bg-[#202226] data-dark:hover:bg-white/[0.1]"
							>
								Actions
								<ArrowFilledRightIcon class="h-2.5 w-2.5" />
							</Button>
						</DropdownMenu.Trigger>
						<DropdownMenu.Content alignOffset={-40} transitionConfig={{ x: 5, y: -5 }}>
							<DropdownMenu.Group>
								<DropdownMenu.Item
									on:click={() => (isAddingColumn = { type: 'input', showDialog: true })}
								>
									<ColumnIcon class="h-3.5 w-3.5 mr-2 mb-[1px]" />
									<span>
										Add
										<span class="text-[#3A73B6] data-dark:text-[#4B91E4]">input</span>
										column
									</span>
								</DropdownMenu.Item>
								<DropdownMenu.Item
									on:click={() => (isAddingColumn = { type: 'output', showDialog: true })}
								>
									<ColumnIcon class="h-3.5 w-3.5 mr-2 mb-[1px]" />
									<span>
										Add
										<span class="text-[#A67835] data-dark:text-[#DA9F47]">output</span>
										column
									</span>
								</DropdownMenu.Item>
							</DropdownMenu.Group>
							{#if selected.length}
								<DropdownMenu.Separator />
								<DropdownMenu.Group>
									{#if selected.length}
										<DropdownMenu.Item
											on:click={() => {
												handleRegenRow(selected.filter((i) => !streamingRows[i]));
												selected = [];
											}}
											class="pl-[5px]"
										>
											<RegenerateIcon class="h-5 w-5 mr-[5px]" />
											Regenerate row
										</DropdownMenu.Item>
									{/if}
									<DropdownMenu.Item on:click={() => (isDeletingRow = selected)}>
										<Trash2 class="h-3.5 w-3.5 mr-2 mb-[2px]" />
										Delete row(s)
									</DropdownMenu.Item>
								</DropdownMenu.Group>
							{/if}
						</DropdownMenu.Content>
					</DropdownMenu.Root>

					<!-- <Button
						on:click={() => alert('open chunk editor')}
						variant="ghost"
						class="flex items-center gap-2 p-0 px-2 h-9 rounded-md border border-[#E5E5E5] data-dark:border-[#666] bg-white data-dark:bg-[#202226] data-dark:hover:bg-white/[0.1]"
					>
						<ChunkEditorIcon class="mt-0.5 h-4 aspect-square" />
						Chunk Editor
					</Button> -->
				{/if}
			</div>
		</div>

		{#if tableData && rows}
			<div inert={isColumnSettingsOpen.showMenu} class="grow flex flex-col w-full min-h-0">
				<div
					role="grid"
					style="grid-template-rows: 46px repeat({rows.length}, min-content);"
					class="grow relative grid px-4 overflow-auto"
				>
					<div
						role="row"
						style="grid-template-columns: 60px repeat({tableData.cols.length}, minmax(320px, 1fr));"
						class="sticky top-0 z-20 h-min grid text-sm border border-[#E5E5E5] data-dark:border-[#333] rounded-lg bg-white data-dark:bg-[#42464E] overflow-hidden"
					>
						<div role="columnheader" class="flex items-center px-4 py-3">
							<Checkbox
								on:checkedChange={() => {
									if (rows) {
										return rows.every((row) => selected.includes(row.ID))
											? (selected = selected.filter((i) => !rows?.some(({ ID }) => ID === i)))
											: (selected = [
													...selected.filter((i) => !rows?.some(({ ID }) => ID === i)),
													...rows.map(({ ID }) => ID)
												]);
									} else return false;
								}}
								checked={rows.every((row) => selected.includes(row.ID))}
								class="h-5 w-5"
							/>
						</div>
						{#each tableData.cols as column, index (column.id)}
							{@const colType = !column.gen_config ? 'input' : 'output'}
							<!-- svelte-ignore a11y-interactive-supports-focus -->
							<!-- svelte-ignore a11y-click-events-have-key-events -->
							<div
								role="columnheader"
								title={column.id}
								on:click={() => {
									if (column.id !== 'ID' && column.id !== 'Updated at') {
										isColumnSettingsOpen = { column, showMenu: true };
									}
								}}
								on:dragover={(e) => {
									if (!RESTRICTED_COLUMNS.includes(column.id)) {
										e.preventDefault();
										hoveredColumnIndex = index;
									}
								}}
								class="flex items-center gap-2 pl-4 pr-5 py-2 cursor-default {isColumnSettingsOpen
									.column?.id == column.id && isColumnSettingsOpen.showMenu
									? 'bg-[#30A8FF33]'
									: ''} {draggingColumn?.id == column.id ? 'opacity-0' : ''}"
							>
								{#if !RESTRICTED_COLUMNS.includes(column.id)}
									<button
										disabled={isReorderLoading}
										on:click|stopPropagation
										on:dragstart={(e) => {
											//@ts-ignore
											let rect = e.target.getBoundingClientRect();
											dragMouseCoords = {
												x: e.clientX,
												y: e.clientY,
												startX: e.clientX - rect.left,
												startY: e.clientY - rect.top,
												//@ts-ignore
												width: e.target.parentElement.offsetWidth
											};
											draggingColumn = column;
											draggingColumnIndex = index;
										}}
										on:drag={(e) => {
											if (e.clientX === 0 && e.clientY === 0) return;
											//@ts-ignore
											dragMouseCoords = { ...dragMouseCoords, x: e.clientX, y: e.clientY };
										}}
										on:dragend={() => {
											dragMouseCoords = null;
											draggingColumn = null;
											draggingColumnIndex = null;
											hoveredColumnIndex = null;
											handleSaveOrder();
										}}
										draggable={true}
										class="cursor-grab disabled:cursor-not-allowed"
									>
										<GripVertical size={18} />
									</button>

									<span
										style="background-color: {colType === 'input'
											? '#CFE8FF'
											: '#FFE3CF'}; color: {colType === 'input' ? '#3A73B6' : '#B6843A'};"
										class="w-min px-1 py-0.5 capitalize text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
									>
										{colType}
									</span>
								{/if}

								<span class="font-medium text-[#666] data-dark:text-white line-clamp-1">
									{column.id}
								</span>

								{#if !RESTRICTED_COLUMNS.includes(column.id)}
									<DropdownMenu.Root>
										<DropdownMenu.Trigger asChild let:builder>
											<Button
												on:click={(e) => e.stopPropagation()}
												builders={[builder]}
												variant="ghost"
												title="Column actions"
												class="ml-auto p-0 h-7 w-7 aspect-square rounded-full"
											>
												<MoreVertIcon class="h-[18px] w-[18px]" />
											</Button>
										</DropdownMenu.Trigger>
										<DropdownMenu.Content alignOffset={-65} transitionConfig={{ x: 5, y: -5 }}>
											<DropdownMenu.Group>
												<DropdownMenu.Item
													on:click={() => (isColumnSettingsOpen = { column, showMenu: true })}
												>
													<TuneIcon class="h-4 w-4 mr-2 mb-[1px]" />
													<span>Open settings</span>
												</DropdownMenu.Item>
											</DropdownMenu.Group>
											<DropdownMenu.Separator />
											<DropdownMenu.Group>
												<DropdownMenu.Item on:click={() => (isDeletingColumn = column.id)}>
													<Trash2 class="h-4 w-4 mr-2 mb-[2px]" />
													<span>Delete column</span>
												</DropdownMenu.Item>
											</DropdownMenu.Group>
										</DropdownMenu.Content>
									</DropdownMenu.Root>
								{/if}
							</div>
						{/each}
					</div>

					<!-- Bandaid fix for no scrolling when no rows -->
					<div
						style="grid-template-columns: 60px repeat({tableData.cols.length}, minmax(320px, 1fr));"
						class="z-0 grid place-items-start h-min max-h-[150px] text-sm pointer-events-none invisible"
					></div>

					{#if rows.length > 0}
						{#each rows as row (row.ID)}
							<div
								role="row"
								style="grid-template-columns: 60px repeat({tableData.cols
									.length}, minmax(320px, 1fr));"
								class="relative z-0 grid place-items-start h-min max-h-[150px] text-sm transition-colors {streamingRows[
									row.ID
								]
									? 'border border-blink-secondary'
									: 'border-l border-l-transparent data-dark:border-l-transparent border-r border-r-transparent data-dark:border-r-transparent border-b border-[#E5E5E5] data-dark:border-[#333]'}"
							>
								<div role="gridcell" class="px-4 py-3">
									<Checkbox
										on:checkedChange={(e) => handleSelectRow(e, row)}
										checked={!!selected.find((i) => i === row.ID)}
										class="h-5 w-5"
									/>
								</div>
								{#each tableData.cols as column}
									{@const editMode =
										isEditingCell &&
										isEditingCell.rowID === row.ID &&
										isEditingCell.columnID === column.id}
									<!-- svelte-ignore a11y-interactive-supports-focus -->
									<div
										role="gridcell"
										tabindex="0"
										on:dblclick={() => {
											if (RESTRICTED_COLUMNS.includes(column.id)) return;
											if (!streamingRows[row.ID]) {
												isEditingCell = { rowID: row.ID, columnID: column.id };
											}
										}}
										on:keydown={(e) => {
											if (RESTRICTED_COLUMNS.includes(column.id)) return;
											if (!editMode && e.key == 'Enter' && !streamingRows[row.ID]) {
												isEditingCell = { rowID: row.ID, columnID: column.id };
											}
										}}
										class="{editMode
											? 'p-0 bg-black/5 data-dark:bg-white/5'
											: 'px-5 py-3 overflow-auto whitespace-pre-line'} h-full max-h-[150px] w-full break-words {isColumnSettingsOpen
											.column?.id == column.id && isColumnSettingsOpen.showMenu
											? 'bg-[#30A8FF17]'
											: ''} hover:bg-black/5 data-dark:hover:bg-white/5 {streamingRows[row.ID] &&
										column.id !== 'ID' &&
										column.id !== 'Updated at' &&
										column.gen_config
											? 'response-cursor'
											: ''}"
									>
										{#if editMode}
											<!-- svelte-ignore a11y-autofocus -->
											<textarea
												autofocus
												value={row[column.id].value}
												on:keydown={(e) => {
													if (e.key === 'Enter' && !e.shiftKey) {
														e.preventDefault();

														handleSaveEdit(e);
													} else if (e.key === 'Escape') {
														isEditingCell = null;
													}
												}}
												on:blur={() => (isEditingCell = null)}
												class="min-h-[150px] h-full w-full px-5 py-3 bg-transparent outline outline-secondary data-dark:outline-[#5b7ee5] resize-none"
											/>
										{:else if column.id === 'ID'}
											{row[column.id]}
										{:else if column.id === 'Updated at'}
											{new Date(row[column.id]).toLocaleString()}
										{:else}
											{row[column.id]?.value === undefined ? '' : row[column.id].value}
										{/if}
									</div>
								{/each}
							</div>
						{/each}
					{:else}
						<div
							class="fixed top-1/2 left-[45%] -translate-x-1/2 -translate-y-1/2 flex flex-col items-center justify-center gap-2 h-full pointer-events-none"
						>
							<NoRowsGraphic class="h-[17rem]" />
							<span class="mt-4 text-lg">Upload Document</span>
							<span class="text-sm text-[#999]">
								Select a document to start generating your table
							</span>
							<Button on:click={handleUploadClick} class="mt-2 rounded-full pointer-events-auto"
								>Browse Document</Button
							>
						</div>
					{/if}
				</div>
			</div>

			<div
				inert={isColumnSettingsOpen.showMenu}
				class="flex items-center justify-between px-4 py-3 min-h-[55px] border-t border-[#E5E5E5] data-dark:border-[#333]"
			>
				<div class="flex items-end gap-6">
					<span class="text-sm font-medium text-[#666] data-dark:text-white">
						Showing {count == 0 ? 0 : perPage * currentPage - perPage + 1}-{perPage * currentPage >
						count
							? count
							: perPage * currentPage} of {count} rows
					</span>

					{#if selected.length}
						<span class="text-xs font-medium text-[#666] data-dark:text-white">
							Selected {selected.length} rows
						</span>
					{/if}
				</div>

				{#if count > 0}
					<Pagination.Root page={currentPage} {count} {perPage} let:pages class="w-[unset] mx-0">
						<Pagination.Content>
							<Pagination.Item>
								<Pagination.PrevButton>
									<ArrowLeftIcon class="h-4 w-4" />
								</Pagination.PrevButton>
							</Pagination.Item>
							{#each pages as page (page.key)}
								{#if page.type === 'ellipsis'}
									<Pagination.Item>
										<Pagination.Ellipsis />
									</Pagination.Item>
								{:else}
									<Pagination.Item>
										<Pagination.Link asChild isActive={currentPage === page.value} {page}>
											<a
												href="?page={page.value}"
												class="inline-flex items-center justify-center rounded-md text-sm font-medium whitespace-nowrap ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-6 w-6"
											>
												{page.value}
											</a>
										</Pagination.Link>
									</Pagination.Item>
								{/if}
							{/each}
							<Pagination.Item>
								<Pagination.NextButton>
									<ArrowRightIcon class="h-4 w-4" />
								</Pagination.NextButton>
							</Pagination.Item>
						</Pagination.Content>
					</Pagination.Root>
				{/if}
			</div>
		{:else if table && table.error == 404}
			<div class="flex items-center justify-center h-full">
				<p class="font-medium text-xl">Table not found</p>
			</div>
		{:else if table && table.error}
			<div class="flex flex-col items-center justify-center gap-2 self-center h-full max-w-[50%]">
				<p class="font-medium text-xl">{table.error} Failed to load table</p>
				<p class="text-sm text-[#999]">{table.message}</p>
			</div>
		{:else}
			<div class="flex items-center justify-center h-full">
				<LoadingSpinner class="h-5 w-5 text-secondary" />
			</div>
		{/if}

		<ColumnSettings bind:isColumnSettingsOpen bind:isDeletingColumn />
	</section>

	<section
		class="relative z-[1] flex flex-col gap-2 min-h-0 bg-white data-dark:bg-[#303338] border-l border-[#DDD] data-dark:border-[#2A2A2A]"
	>
		<!-- Close right dock button -->
		<div
			class="absolute top-1/2 -translate-y-1/2 -left-16 flex items-center justify-end h-[80%] w-16 overflow-hidden pointer-events-none"
		>
			<button
				bind:this={rightDockButton}
				title="Show/hide knowledge table history"
				on:click={() => ($showRightDock = !$showRightDock)}
				on:focusin={() => (showRightDockButton = true)}
				on:focusout={() => (showRightDockButton = false)}
				class={`p-1 bg-white data-dark:bg-[#303338] border border-[#DDD] data-dark:border-[#2A2A2A] rounded-l-xl ${
					showRightDockButton ? 'translate-x-0' : 'translate-x-11'
				} transition-transform duration-300 pointer-events-auto`}
			>
				<DblArrowRightIcon class={`w-8 h-8 ${!$showRightDock && 'rotate-180'}`} />
			</button>
		</div>

		<Button
			disabled={!$showRightDock}
			variant="outline"
			title="New table"
			on:click={() => (isAddingTable = true)}
			class="flex items-center gap-3 m-4 mx-6 mt-10 p-4 text-secondary hover:text-secondary text-center border-2 border-secondary bg-transparent hover:bg-black/[0.09] data-dark:hover:bg-white/[0.1] rounded-lg whitespace-nowrap overflow-hidden"
		>
			<AddIcon class="w-3 h-3" />
			New table
		</Button>

		<KnowledgeTables bind:isDeletingTable />
	</section>
</div>

<!-- Dragged item -->
{#if dragMouseCoords && draggingColumn}
	{@const colType = !draggingColumn.gen_config /* || Object.keys(column.gen_config).length === 0 */
		? 'input'
		: 'output'}
	<div
		style="top: {dragMouseCoords.y - dragMouseCoords.startY - 15}px; left: {dragMouseCoords.x -
			dragMouseCoords.startX -
			15}px; width: {dragMouseCoords.width}px;"
		class="absolute z-[9999] flex items-center gap-2 pl-4 pr-5 py-2 bg-white data-dark:bg-[#42464E] pointer-events-none"
	>
		<button>
			<GripVertical size={18} />
		</button>

		<span
			style="background-color: {colType === 'input' ? '#CFE8FF' : '#FFE3CF'}; color: {colType ===
			'input'
				? '#3A73B6'
				: '#B6843A'};"
			class="w-min px-1 py-0.5 capitalize text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
		>
			{colType}
		</span>

		<span class="font-medium text-sm text-[#666] data-dark:text-white line-clamp-1">
			{draggingColumn.id}
		</span>

		{#if !RESTRICTED_COLUMNS.includes(draggingColumn.id)}
			<Button
				variant="ghost"
				title="Column settings"
				class="ml-auto p-0 h-7 w-7 aspect-square rounded-full"
			>
				<MoreVertIcon class="h-[18px] w-[18px]" />
			</Button>
		{/if}
	</div>
{/if}

<AddTableDialog bind:isAddingTable />
<AddColumnDialog bind:isAddingColumn />
<AddRowDialog bind:isAddingRow bind:isLoadingAddRow {addRowFunction} />
<DeleteDialogs bind:isDeletingTable bind:isDeletingColumn bind:isDeletingRow />
<UploadingFileDialog {isUploadingFile} />
