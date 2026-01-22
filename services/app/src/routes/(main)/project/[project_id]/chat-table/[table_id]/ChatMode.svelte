<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount, tick } from 'svelte';
	import axios from 'axios';
	import { v4 as uuidv4 } from 'uuid';
	import { ArrowDownToLine, ArrowUp, AudioLines, ChevronRight, FileText } from '@lucide/svelte';
	import { browser } from '$app/environment';
	import { page } from '$app/state';
	import { getTableState } from '$lib/components/tables/tablesState.svelte';
	import converter from '$lib/showdown';
	import { chatCitationPattern, fileColumnFiletypes } from '$lib/constants';
	import { citationReplacer, cn } from '$lib/utils';
	import logger from '$lib/logger';
	import type {
		ChatReferences,
		ChatThread,
		ChatThreads,
		Conversation,
		GenTable,
		GenTableStreamEvent,
		Thread
	} from '$lib/types';

	import RowStreamIndicator from '$lib/components/preset/RowStreamIndicator.svelte';
	import { ChatFilePreview, ChatThumbsFetch } from '$lib/components/chat';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import SendIcon from '$lib/icons/SendIcon.svelte';
	import RegenerateIcon from '$lib/icons/RegenerateIcon.svelte';
	import MultiturnChatIcon from '$lib/icons/MultiturnChatIcon.svelte';
	import TuneIcon from '$lib/icons/TuneIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	const tableState = getTableState();

	interface Props {
		tableData: GenTable | undefined;
		tableThread: ChatThreads['threads'];
		threadLoaded: boolean;
		generationStatus: string[] | null;
		refetchTable: (hideColumnSettings?: boolean) => Promise<void>;
	}

	let {
		tableData,
		tableThread = $bindable(),
		threadLoaded,
		generationStatus = $bindable(),
		refetchTable
	}: Props = $props();

	/* let thread: ChatRequest['messages'] = [];
	$: table, resetThread();
	const resetThread = async () => {
		const tableRes = await table;
		thread = tableRes.thread ?? [];
		isLoading = false;
	}; */

	let uploadColumns: Record<string, { uri: string; url: string }> = $state({});
	let loadedStreams: Record<string, Record<string, string[]>> = $state({});
	let latestStreams: Record<string, Record<string, string>> = $state({});
	let reasoningContentStreams: Record<string, Record<string, string>> = $state({});
	let loadedReferences: Record<string, Record<string, ChatReferences>> | null = null;

	let showRawTexts = $state(false);

	let chatWindow: HTMLDivElement | null = $state(null);
	let isLoading = true;

	//Chatbar
	let chatForm: HTMLFormElement | null = $state(null);
	let chat: HTMLTextAreaElement | null = $state(null);

	let chatMessage = $state('');
	let isResizing = $state(false);
	let isResized = $state(false);

	let editingContent: {
		rowID: string;
		columnID: string;
		fileColumns: Record<string, { uri: string; url: string }>;
	} | null = $state(null);

	let longestThreadCol = $derived(
		Object.keys(tableThread).reduce(
			(a, b) =>
				Array.isArray(tableThread[b].thread) &&
				(!a || tableThread[b].thread.length > tableThread[a].thread.length)
					? b
					: a,
			''
		)
	);

	let fileColumns = $derived(
		tableData?.cols.filter(
			(col) => col.dtype === 'image' || col.dtype === 'audio' || col.dtype === 'document'
		) ?? []
	);
	let uris: { [rowID: string]: { [colID: string]: string } } = $derived({
		...Object.fromEntries(
			Object.entries(tableThread)
				.map(([col, thread]) =>
					thread.thread
						.map((val) =>
							typeof val.content === 'string'
								? []
								: [
										[
											val.row_id,
											Object.fromEntries(
												val.content
													.map((content) =>
														content.type === 'text' ? [] : [[content.column_name, content.uri]]
													)
													.flat()
											)
										]
									]
						)
						.flat()
				)
				.flat()
		)
		// ...{
		// 	new: Object.fromEntries(
		// 		Object.entries(chatState.uploadColumns).map(([col, val]) => [col, val.uri])
		// 	)
		// }
	});
	let rowThumbs: { [uri: string]: string } = $state({});
	let showFilePreview = $state<string | null>(null);

	function resizeChat() {
		if (isResized || !chat) return; //? Prevents textarea from resizing by typing when chatbar is resized by user
		chat.style.height = '3rem';
		chat.style.height = Math.min(chat.scrollHeight, 180) + 'px';
	}

	function interceptSubmit(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			isResized = false;
			chatForm?.requestSubmit();
		}
	}

	async function handleChatSubmit(e: Event) {
		e.preventDefault();
		if (!chat || !chatWindow) return;
		if (!tableData || !threadLoaded) return;
		if (generationStatus || !chatMessage.trim()) return;

		const cachedPrompt = chatMessage;
		const cachedFiles = structuredClone($state.snapshot(uploadColumns));
		chatMessage = '';
		uploadColumns = {};

		// chatMessage = '';
		chat.style.height = '3rem';

		//? Add user message to the chat
		tableThread = Object.fromEntries(
			Object.entries(tableThread).map(([outCol, thread]) => [
				outCol,
				{
					...thread,
					thread: [
						...thread.thread,
						{
							row_id: uuidv4(),
							role: 'user',
							content: [
								{
									type: 'text' as const,
									text: cachedPrompt
								},
								...Object.entries(cachedFiles).map(([uploadColumn, val]) => ({
									type: 'input_s3' as const,
									uri: val.uri,
									column_name: uploadColumn
								}))
							],
							name: null,
							user_prompt: cachedPrompt,
							references: null
						}
					]
				}
			])
		);

		generationStatus = ['new'];
		loadedStreams = {
			new: Object.fromEntries(
				tableData.cols
					.map((col) =>
						col.gen_config?.object === 'gen_config.llm' && col.gen_config.multi_turn
							? [[col.id, []]]
							: []
					)
					.flat()
			)
		};
		latestStreams = {
			new: Object.fromEntries(
				tableData.cols
					.map((col) =>
						col.gen_config?.object === 'gen_config.llm' && col.gen_config.multi_turn
							? [[col.id, '']]
							: []
					)
					.flat()
			)
		};

		//? Show user message
		await tick();
		chatWindow.scrollTop = chatWindow.scrollHeight;

		//? Send message to the server
		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/chat/rows/add`, {
			method: 'POST',
			headers: {
				Accept: 'text/event-stream',
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id ?? ''
			},
			body: JSON.stringify({
				table_id: page.params.table_id,
				data: [
					{
						User: cachedPrompt
					}
				],
				stream: true
			})
		});

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error('CHATTBL_CHAT_ADD', responseBody);
			toast.error('Failed to add row', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
			tableThread = Object.fromEntries(
				Object.entries(tableThread).map(([outCol, thread]) => [
					outCol,
					{
						...thread,
						thread: thread.thread.slice(0, -1)
					}
				])
			);
			chatMessage = cachedPrompt;
		} else {
			const { row_id } = await parseStream(
				response.body!.pipeThrough(new TextDecoderStream()).getReader(),
				true
			);

			loadedStreams = Object.fromEntries(
				Object.entries(loadedStreams).map(([row, colStreams]) => [
					row,
					Object.fromEntries(
						Object.entries(colStreams).map(([col, streams]) => [
							col,
							[...streams, latestStreams[row][col]]
						])
					)
				])
			);

			tableThread = Object.fromEntries(
				Object.entries(tableThread).map(([outCol, thread]) => {
					const loadedStreamCol = loadedStreams.new[outCol];
					const colReferences = loadedReferences?.new?.[outCol] ?? null;
					const userPrompt = thread.thread.at(-1)!;

					return [
						outCol,
						{
							...thread,
							thread: [
								...thread.thread.slice(0, -1),
								{
									...userPrompt,
									row_id
								},
								{
									row_id,
									role: 'assistant',
									content: [
										{
											type: 'text',
											text: loadedStreamCol.join('')
										}
									],
									name: null,
									user_prompt: null,
									references: colReferences
								}
							]
						}
					];
				})
			);

			refetchTable();
		}

		generationStatus = null;
		loadedStreams = {};
		latestStreams = {};
	}

	async function parseStream(reader: ReadableStreamDefaultReader<string>, newMessage = false) {
		let rowID = '';
		let buffer = '';
		let renderCount = 0;
		// eslint-disable-next-line no-constant-condition
		while (true) {
			try {
				const { value, done } = await reader.read();
				if (done) break;

				buffer += value;
				const lines = buffer.split('\n'); //? Split by \n to handle collation
				buffer = lines.pop() || '';

				let parsedEvent:
					| { event: 'metadata'; data: Conversation }
					| { event: undefined; data: GenTableStreamEvent }
					| undefined = undefined;
				for (const line of lines) {
					if (line === '') {
						if (parsedEvent) {
							if (parsedEvent.event) {
								// n/a
							} else if (parsedEvent.data.object === 'gen_table.completion.chunk') {
								if (parsedEvent.data.choices[0].finish_reason) {
									switch (parsedEvent.data.choices[0].finish_reason) {
										case 'error': {
											logger.error('CHAT_MESSAGE_ADDSTREAM', parsedEvent.data);
											console.error('STREAMING_ERROR', parsedEvent.data);
											alert(
												`Error while streaming: ${parsedEvent.data.choices[0].message.content}`
											);
											break;
										}
									}
								} else {
									rowID = parsedEvent.data.row_id;
									const streamDataRowID = newMessage ? 'new' : rowID;

									/** Used if showing reasoning content in chat window */
									if (parsedEvent.data.choices[0]?.message?.reasoning_content) {
										if (!reasoningContentStreams[streamDataRowID]) {
											reasoningContentStreams[streamDataRowID] = {};
										}

										if (
											!reasoningContentStreams[streamDataRowID][parsedEvent.data.output_column_name]
										) {
											reasoningContentStreams[streamDataRowID][
												parsedEvent.data.output_column_name
											] = '';
										}

										reasoningContentStreams[streamDataRowID][parsedEvent.data.output_column_name] +=
											parsedEvent.data.choices[0]?.message?.reasoning_content ?? '';
									}

									if (parsedEvent.data.choices[0]?.message?.content) {
										if (loadedStreams[streamDataRowID][parsedEvent.data.output_column_name]) {
											if (renderCount++ >= 20) {
												loadedStreams[streamDataRowID][parsedEvent.data.output_column_name] = [
													...loadedStreams[streamDataRowID][parsedEvent.data.output_column_name],
													latestStreams[streamDataRowID][parsedEvent.data.output_column_name] +
														(parsedEvent.data.choices[0]?.message?.content ?? '')
												];
												latestStreams[streamDataRowID][parsedEvent.data.output_column_name] = '';
											} else {
												latestStreams[streamDataRowID][parsedEvent.data.output_column_name] +=
													parsedEvent.data.choices[0]?.message?.content ?? '';
											}
										}
									}

									/** Stream output details dialog */
									if (
										tableState.showOutputDetails.activeCell?.rowID === streamDataRowID &&
										tableState.showOutputDetails.activeCell?.columnID ===
											parsedEvent.data.output_column_name
									) {
										tableState.showOutputDetails = {
											...tableState.showOutputDetails,
											message: {
												chunks: tableState.showOutputDetails.message?.chunks ?? [],
												error: tableState.showOutputDetails.message?.error ?? null,
												content:
													(tableState.showOutputDetails.message?.content ?? '') +
													(parsedEvent.data.choices[0].message.content ?? '')
											},
											reasoningContent:
												(tableState.showOutputDetails.reasoningContent ?? '') +
												(parsedEvent.data.choices[0].message.reasoning_content ?? '')
										};
									}

									scrollChatToBottom();
								}
							} else if (parsedEvent.data.object === 'gen_table.references') {
								rowID = parsedEvent.data.row_id;
								const streamDataRowID = newMessage ? 'new' : rowID;

								loadedReferences = {
									...(loadedReferences ?? {}),
									[streamDataRowID]: {
										...((loadedReferences ?? {})[streamDataRowID] ?? {}),
										[parsedEvent.data.output_column_name]:
											parsedEvent.data as unknown as ChatReferences
									}
								};

								/** Add references to output details if active */
								if (
									tableState.showOutputDetails.activeCell?.rowID === streamDataRowID &&
									tableState.showOutputDetails.activeCell?.columnID ===
										parsedEvent.data.output_column_name
								) {
									tableState.showOutputDetails = {
										...tableState.showOutputDetails,
										message: {
											chunks: (parsedEvent.data as unknown as ChatReferences).chunks ?? [],
											error: null,
											content: tableState.showOutputDetails.message?.content ?? ''
										}
									};
								}
							} else {
								console.warn('Unknown event data:', parsedEvent.data);
							}
						} else {
							console.warn('Unknown event object:', parsedEvent);
						}
					} else if (line.startsWith('data: ')) {
						if (line.slice(6) === '[DONE]') break;
						//@ts-expect-error missing type
						parsedEvent = { ...(parsedEvent ?? {}), data: JSON.parse(line.slice(6)) };
					} else if (line.startsWith('event: ')) {
						//@ts-expect-error missing type
						parsedEvent = { ...(parsedEvent ?? {}), event: line.slice(7) };
					}
				}
			} catch (err) {
				logger.error('CHAT_MESSAGE_ADDSTREAM', err);
				console.error(err);
				break;
			}
		}

		return { row_id: rowID };
	}

	onMount(() => {
		if (chatWindow) chatWindow.scrollTop = chatWindow.scrollHeight;
	});

	const scrollChatToBottom = async () => {
		if (!browser) return;

		if (
			chatWindow &&
			(chatWindow.scrollHeight - chatWindow.clientHeight - chatWindow.scrollTop < 100 ||
				!generationStatus)
		) {
			await tick();
			await tick();
			chatWindow.scrollTop = chatWindow.scrollHeight;
		}
	};
	$effect(() => {
		loadedStreams;
		scrollChatToBottom();
	});

	function handleResize(e: MouseEvent) {
		if (!chat) return;
		if (!isResizing) return;

		const chatBottomSpace = 74;
		const chatbarMaxHeight = window.innerHeight * 0.65;
		const chatbarHeight = window.innerHeight - e.clientY - chatBottomSpace;

		chat.style.height =
			(chatbarHeight >= chatbarMaxHeight ? chatbarMaxHeight : chatbarHeight) + 'px';

		isResized = true;
	}

	function handleCustomBtnClick(e: MouseEvent) {
		const target = e.target as HTMLElement;
		if (target.classList.contains('copy-code')) {
			const code = target.parentElement?.parentElement?.querySelector('code');
			if (code) {
				navigator.clipboard.writeText(code.innerText);

				const copyIcon = target.querySelector('.copy-icon');
				const checkIcon = target.querySelector('.check-icon');
				if (copyIcon && checkIcon) {
					(copyIcon as HTMLElement).style.opacity = '0';
					(checkIcon as HTMLElement).style.opacity = '1';

					new Promise((resolve) => setTimeout(resolve, 1000)).then(() => {
						(copyIcon as HTMLElement).style.opacity = '1';
						(checkIcon as HTMLElement).style.opacity = '0';
					});
				}
			}
		} else if (target.classList.contains('citation-btn')) {
			const columnID = target.getAttribute('data-column');
			const rowID = target.getAttribute('data-row');
			const chunkID = target.getAttribute('data-citation');
			if (columnID && rowID && chunkID) {
				// showChatControls = { open: false, value: null };

				const threadItem = tableThread[columnID]?.thread?.find(
					(item) => item.references && item.row_id === rowID
				);
				tableState.showOutputDetails = {
					open: true,
					activeCell: { columnID, rowID },
					activeTab: 'references',
					message: {
						content:
							typeof threadItem?.content === 'string'
								? threadItem.content
								: (threadItem?.content
										.filter((c) => c.type === 'text')
										.map((c) => c.text)
										.join('') ?? ''),
						error: null,
						chunks: threadItem?.references?.chunks ?? []
					},
					reasoningContent: threadItem?.reasoning_content ?? null,
					reasoningTime: threadItem?.reasoning_time ?? null,
					expandChunk: chunkID,
					preview: null
				};
			}
		}
	}

	async function getRawFile(fileUri: string) {
		if (!fileUri) return;

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/files/url/raw`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				uris: [fileUri]
			})
		});
		const responseBody = await response.json();

		if (response.ok) {
			window.open(responseBody.urls[0], '_blank');
		} else {
			if (response.status !== 404) {
				logger.error('GETRAW', responseBody);
			}
			toast.error('Failed to get raw file', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}
	}

	function getNewMessageAsThreads(): typeof tableThread {
		const longestThreadCol = Object.keys(tableThread).reduce(
			(a, b) =>
				Array.isArray(tableThread[b].thread) &&
				(!a || tableThread[b].thread.length > tableThread[a].thread.length)
					? b
					: a,
			''
		);
		const longestThreadColLen = tableThread[longestThreadCol]?.thread?.length ?? 0;
		return generationStatus?.includes('new')
			? Object.fromEntries(
					tableData!.cols
						.map((col) =>
							col.gen_config?.object === 'gen_config.llm' && col.gen_config.multi_turn
								? [
										[
											col.id,
											{
												object: 'chat.thread',
												thread: [
													...new Array(longestThreadColLen).fill(null),
													{
														reasoning_content: reasoningContentStreams.new?.[col.id] ?? null,
														reasoning_time: null,
														row_id: 'new',
														role: 'assistant',
														content:
															(loadedStreams.new?.[col.id]?.join('') ?? '') +
															(latestStreams.new?.[col.id] ?? ''),
														name: null,
														user_prompt: null,
														references: null
													}
												]
											} as ChatThread
										]
									]
								: []
						)
						.flat()
				)
			: {};
	}

	let dragContainer = $state<HTMLElement | null>(null);
	let filesDragover = $state(false);
	function handleSelectFiles(files: File[], editing = false) {
		dragContainer
			?.querySelectorAll('input[type="file"]')
			?.forEach((el) => ((el as HTMLInputElement).value = ''));

		if (files.length === 0) return;
		if (
			Object.values(editing ? (editingContent?.fileColumns ?? {}) : uploadColumns).filter(
				(val) => val.uri
			).length >= fileColumns.length
		) {
			alert('No more files can be uploaded: all columns filled.');
			return;
		}

		if (files.length === 0) return;
		if (files.length > 1) {
			alert('Cannot upload multiple files in one column');
			return;
		}

		if (
			files.some(
				(file) =>
					!fileColumnFiletypes
						.filter(({ type }) =>
							fileColumns
								.filter(
									(c) =>
										!(editing ? (editingContent?.fileColumns ?? {}) : uploadColumns)[
											c.id
										]?.uri?.trim()
								)
								.map((c) => c.dtype)
								.includes(type)
						)
						.map(({ ext }) => ext)
						.includes('.' + (file.name.split('.').pop() ?? '').toLowerCase())
			)
		) {
			alert(
				`Files must be of type: ${fileColumnFiletypes
					.filter(({ type }) =>
						fileColumns
							.filter(
								(c) =>
									!(editing ? (editingContent?.fileColumns ?? {}) : uploadColumns)[
										c.id
									]?.uri?.trim()
							)
							.map((c) => c.dtype)
							.includes(type)
					)
					.map(({ ext }) => ext)
					.join(', ')
					.replaceAll('.', '')}`
			);
			return;
		}

		handleSaveFile(files, editing);
	}
	const handleDragLeave = () => (filesDragover = false);

	async function handleSaveFile(files: File[], editing = false) {
		const formData = new FormData();
		formData.append('file', files[0]);

		const nextAvailableCol = fileColumns.find(
			(col) =>
				!(editing ? (editingContent?.fileColumns ?? {}) : uploadColumns)[col.id]?.uri &&
				fileColumnFiletypes
					.filter(({ type }) => col.dtype === type)
					.map(({ ext }) => ext)
					.includes('.' + (files[0].name.split('.').pop() ?? '').toLowerCase())
		);
		if (!nextAvailableCol)
			return alert('No more files of this type can be uploaded: all columns filled.');

		if (editing) {
			if (editingContent) {
				editingContent.fileColumns[nextAvailableCol.id] = {
					uri: 'loading',
					url: ''
				};
			}
		} else {
			uploadColumns[nextAvailableCol.id] = {
				uri: 'loading',
				url: ''
			};
		}

		try {
			const uploadRes = await axios.post(`${PUBLIC_JAMAI_URL}/api/owl/files/upload`, formData, {
				headers: {
					'Content-Type': 'multipart/form-data',
					'x-project-id': page.url.searchParams.get('project_id') ?? page.params.project_id
				}
			});

			if (uploadRes.status !== 200) {
				logger.error('CHAT_FILE_UPLOAD', {
					file: files[0].name,
					response: uploadRes.data
				});
				alert(
					'Failed to upload file: ' +
						(uploadRes.data.message || JSON.stringify(uploadRes.data)) +
						`\nRequest ID: ${uploadRes.data.request_id}`
				);
				return;
			} else {
				const urlResponse = await fetch(`/api/owl/files/url/thumb`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
						'x-project-id': page.params.project_id ?? ''
					},
					body: JSON.stringify({
						uris: [uploadRes.data.uri]
					})
				});
				const urlBody = await urlResponse.json();

				if (urlResponse.ok) {
					if (editing) {
						if (editingContent) {
							editingContent.fileColumns[nextAvailableCol.id] = {
								uri: uploadRes.data.uri,
								url: urlBody.urls[0]
							};
						}
					} else {
						uploadColumns[nextAvailableCol.id] = {
							uri: uploadRes.data.uri,
							url: urlBody.urls[0]
						};

						console.log(uploadColumns);
					}
				} else {
					if (editing) {
						if (editingContent) {
							editingContent.fileColumns[nextAvailableCol.id] = {
								uri: uploadRes.data.uri,
								url: ''
							};
						}
					} else {
						uploadColumns[nextAvailableCol.id] = { uri: uploadRes.data.uri, url: '' };
					}
					toast.error('Failed to retrieve thumbnail', {
						id: urlBody.message || JSON.stringify(urlBody),
						description: CustomToastDesc as any,
						componentProps: {
							description: urlBody.message || JSON.stringify(urlBody),
							requestID: urlBody.request_id
						}
					});
				}
			}
		} catch (err) {
			if (!(err instanceof axios.CanceledError && err.code == 'ERR_CANCELED')) {
				//@ts-expect-error AxiosError
				logger.error('CHAT_FILE_UPLOAD', err?.response?.data);
				alert(
					'Failed to upload file: ' +
						//@ts-expect-error AxiosError
						(err?.response?.data.message || JSON.stringify(err?.response?.data)) +
						//@ts-expect-error AxiosError
						`\nRequest ID: ${err?.response?.data?.request_id}`
				);
			}
		}
	}
</script>

<svelte:document
	onmousemove={handleResize}
	onmouseup={() => (isResizing = false)}
	onclick={handleCustomBtnClick}
	onkeydown={(e) => {
		if (
			//@ts-ignore
			e.target.tagName !== 'INPUT' &&
			//@ts-ignore
			e.target.tagName !== 'TEXTAREA' &&
			e.shiftKey &&
			(e.key === 'r' || e.key === 'R')
		) {
			showRawTexts = !showRawTexts;
		}
	}}
/>

<div
	bind:this={chatWindow}
	data-testid="chat-window"
	id="chat-window"
	class="relative mx-auto flex w-full max-w-6xl grow snap-x snap-mandatory flex-col gap-4 overflow-auto px-2.5 pt-3"
>
	{#if threadLoaded}
		{@const multiturnCols = Object.keys(tableThread)}
		{@const longestThreadColLen =
			(tableThread[longestThreadCol]?.thread?.length ?? 0) +
			(generationStatus?.includes('new') &&
			(tableThread[longestThreadCol]?.thread?.length ?? 0) !== 0
				? 1
				: 0)}
		{#each Array(longestThreadColLen).fill('') as _, index}
			{@const threadsEntries = [
				...Object.entries(tableThread),
				...Object.entries(getNewMessageAsThreads())
			]}
			<!-- temp -->
			{@const isEditingCell = false}
			{#if threadsEntries.some(([, thread]) => thread.thread[index]?.role !== 'system')}
				<div
					class="group/message-container message-container flex flex-[0_0_auto] gap-3 transition-[padding]"
				>
					{#each threadsEntries as [column, thread]}
						{@const threadItem = thread.thread[index]}
						{#if threadItem && threadItem.role !== 'system'}
							{#if threadItem.role === 'user'}
								<div
									data-role="user"
									class={cn(
										'ml-auto flex snap-center flex-col gap-1 transition-[padding]',
										multiturnCols.length > 1
											? 'min-w-full @3xl/chat:min-w-[50%] supports-[not(container-type:inline-size)]:xl:min-w-[50%]'
											: 'max-w-full',
										multiturnCols.length > 2
											? '@6xl/chat:min-w-[33.333%] supports-[not(container-type:inline-size)]:3xl:min-w-[33.333%]'
											: '',
										multiturnCols.length == 1
											? '@5xl/chat:pl-[20%] supports-[not(container-type:inline-size)]:xl:pl-[20%]'
											: 'last:pr-2.5'
									)}
								>
									<div class="flex items-end justify-end">
										<div
											class:invisible={isEditingCell}
											class="flex items-center opacity-0 transition-opacity group-hover/message-container:opacity-100"
										>
											<!-- <Button
												variant="ghost"
												title="Edit content"
												onclick={async () => {
													// chatState.editingContent = {
													// 	rowID: threadItem.row_id,
													// 	columnID: 'User',
													// 	fileColumns:
													// 		typeof threadItem.content !== 'string'
													// 			? Object.fromEntries(
													// 					threadItem.content
													// 						.filter((c) => c.type === 'input_s3')
													// 						.map((c) => [
													// 							c.column_name,
													// 							{ uri: c.uri, url: rowThumbs[c.uri] }
													// 						])
													// 				)
													// 			: {}
													// };
													// await tick();
													// resizeEditContent();
												}}
												class="h-7 w-7 p-0 text-[#98A2B3]"
											>
												<EditIcon class="h-3.5 w-3.5" />
											</Button> -->
										</div>
									</div>

									<div
										data-testid="chat-message"
										class:w-full={multiturnCols.length > 1}
										class="group relative flex max-w-full scroll-my-2 flex-col gap-2 self-end rounded-xl bg-white p-4 data-dark:bg-[#444]"
									>
										{#if isEditingCell}
											<!-- {@render cellContentEditor(threadItem)} -->
										{:else if typeof threadItem.content === 'string'}
											<div
												class="whitespace-pre-wrap text-sm [overflow-wrap:anywhere] focus:outline-none"
											>
												{#if showRawTexts}
													{threadItem.content}
												{:else}
													{threadItem.user_prompt}
												{/if}
											</div>
										{:else}
											{#if threadItem.content.some((c) => c.type === 'input_s3' && c.uri)}
												<div class="flex flex-wrap gap-2">
													{#each threadItem.content as content}
														{#if content.type === 'input_s3'}
															{#if content.uri}
																{@const fileType = fileColumnFiletypes.find(({ ext }) =>
																	content.uri.toLowerCase().endsWith(ext)
																)?.type}
																{@const fileUrl = rowThumbs[content.uri]}
																<div class="group/image relative">
																	<button
																		title={content.uri.split('/').pop()}
																		onclick={() => (showFilePreview = content.uri)}
																		class="flex h-36 w-36 items-center justify-center overflow-hidden rounded-xl bg-[#BF416E]"
																	>
																		{#if fileUrl}
																			{#if fileType === 'image'}
																				<img
																					src={fileUrl}
																					alt=""
																					class="z-0 h-full w-full object-cover"
																				/>
																			{:else if fileType === 'audio'}
																				<AudioLines class="h-16 w-16 text-white" />
																			{:else if fileType === 'document'}
																				<img
																					src={fileUrl}
																					alt=""
																					class="z-0 max-w-full object-contain"
																				/>
																			{/if}
																		{/if}
																	</button>

																	<div
																		class="absolute right-1 top-1 flex gap-1 opacity-0 transition-opacity group-focus-within/image:opacity-100 group-hover/image:opacity-100"
																	>
																		<Button
																			variant="ghost"
																			title="Download file"
																			onclick={() => getRawFile(content.uri)}
																			class="aspect-square h-6 rounded-md border border-[#F2F4F7] bg-white p-0 text-[#667085] shadow-[0px_1px_3px_0px_rgba(16,24,40,0.1)] hover:text-[#667085]"
																		>
																			<ArrowDownToLine class="h-3.5 w-3.5" />
																		</Button>
																	</div>
																</div>
															{/if}
														{/if}
													{/each}
												</div>
											{/if}

											<p
												class="whitespace-pre-wrap text-sm [overflow-wrap:anywhere] focus:outline-none"
											>
												{#if showRawTexts}
													{@const textContent = threadItem.content
														.filter((c) => c.type === 'text')
														.map((c) => c.text)
														.join('')}
													{typeof threadItem.content === 'string'
														? threadItem.content
														: textContent}
												{:else}
													{threadItem.user_prompt}
												{/if}
											</p>
										{/if}
									</div>

									{#if isEditingCell}
										<!-- {@render cellContentEditorControls()} -->
									{/if}
								</div>
							{:else if threadItem.role === 'assistant'}
								<!-- {@const isEditingCell =
											chatState.editingContent?.rowID === threadItem.row_id &&
											chatState.editingContent?.columnID === column} -->
								<div
									data-role="assistant"
									class={cn(
										'group/message-container flex flex-col gap-1 transition-[padding]',
										multiturnCols.length > 1
											? 'min-w-full @3xl/chat:min-w-[50%] supports-[not(container-type:inline-size)]:xl:min-w-[50%]'
											: 'max-w-full',
										multiturnCols.length > 2
											? '@6xl/chat:min-w-[33.333%] supports-[not(container-type:inline-size)]:3xl:min-w-[33.333%]'
											: '',
										multiturnCols.length == 1
											? '@5xl/chat:pr-[20%] supports-[not(container-type:inline-size)]:xl:pr-[20%]'
											: 'last:pr-2.5'
									)}
								>
									<div class="flex items-end justify-between px-4">
										<div class="flex items-center gap-2 text-sm">
											<span class="line-clamp-1 font-medium text-[#98A2B3]">
												{column}
											</span>
										</div>

										<div
											class:invisible={isEditingCell}
											class="flex items-center opacity-0 transition-opacity group-hover/message-container:opacity-100"
										>
											<!-- <Button
												variant="ghost"
												title="Edit content"
												onclick={async () => {
													// chatState.editingContent = {
													// 	rowID: threadItem.row_id,
													// 	columnID: column,
													// 	fileColumns:
													// 		typeof threadItem.content !== 'string'
													// 			? Object.fromEntries(
													// 					threadItem.content
													// 						.filter((c) => c.type === 'input_s3')
													// 						.map((c) => [
													// 							c.column_name,
													// 							{ uri: c.uri, url: rowThumbs[c.uri] }
													// 						])
													// 				)
													// 			: {}
													// };
													// await tick();
													// resizeEditContent();
												}}
												class="h-7 w-7 p-0 text-[#98A2B3]"
											>
												<EditIcon class="h-3.5 w-3.5" />
											</Button>

											<Button
												variant="ghost"
												title="Regenerate message"
												onclick={() => /* chatState.regenMessage(threadItem.row_id) */ {}}
												class="h-7 w-7 p-0 text-[#98A2B3]"
											>
												<RegenerateIcon class="h-6 w-6" />
											</Button> -->

											{#if threadItem.references}
												<Button
													variant="ghost"
													title="Show references"
													onclick={() => {
														// showChatControls = { open: false, value: null };
														tableState.showOutputDetails = {
															open: true,
															activeCell: { columnID: column, rowID: threadItem.row_id },
															activeTab: 'references',
															message: {
																content:
																	typeof threadItem?.content === 'string'
																		? threadItem.content
																		: (threadItem?.content
																				.filter((c) => c.type === 'text')
																				.map((c) => c.text)
																				.join('') ?? ''),
																error: null,
																chunks: threadItem?.references?.chunks ?? []
															},
															reasoningContent: threadItem.reasoning_content ?? null,
															reasoningTime: threadItem.reasoning_time ?? null,
															expandChunk: null,
															preview: null
														};
													}}
													class="h-7 w-7 p-0 text-[#98A2B3]"
												>
													<FileText class="h-4 w-4" />
												</Button>
											{/if}
										</div>
									</div>

									{#if generationStatus?.includes(threadItem.row_id)}
										<div class="mt-1 flex items-center gap-2 px-4">
											<RowStreamIndicator />

											{#if reasoningContentStreams[threadItem.row_id]?.[column] && !(loadedStreams[threadItem.row_id]?.[column]?.join('') ?? '') && !(latestStreams[threadItem.row_id]?.[column] ?? '')}
												<button
													onclick={() => {
														// showChatControls = { open: false, value: null };
														tableState.showOutputDetails = {
															open: true,
															activeCell: { columnID: column, rowID: threadItem.row_id },
															activeTab: 'thinking',
															message: {
																content:
																	typeof threadItem.content === 'string'
																		? threadItem.content
																		: (threadItem.content.find((c) => c.type === 'text')?.text ??
																			''),
																error: null,
																chunks:
																	loadedReferences?.[threadItem.row_id]?.[column]?.chunks ?? []
															},
															reasoningContent:
																reasoningContentStreams[threadItem.row_id]?.[column] ?? null,
															reasoningTime: null,
															expandChunk: null,
															preview: null
														};
													}}
													class="flex items-center gap-2 text-[#98A2B3] transition-colors hover:text-[#344054]"
												>
													<span class="text-xs font-medium"> Thinking... </span>
													<ChevronRight size={12} />
												</button>
											{/if}
										</div>
									{:else if threadItem.reasoning_content}
										<button
											onclick={() => {
												// showChatControls = { open: false, value: null };
												tableState.showOutputDetails = {
													open: true,
													activeCell: { columnID: column, rowID: threadItem.row_id },
													activeTab: 'thinking',
													message: {
														content:
															typeof threadItem?.content === 'string'
																? threadItem.content
																: (threadItem?.content
																		.filter((c) => c.type === 'text')
																		.map((c) => c.text)
																		.join('') ?? ''),
														error: null,
														chunks: threadItem?.references?.chunks ?? []
													},
													reasoningContent: threadItem.reasoning_content ?? null,
													reasoningTime: threadItem.reasoning_time ?? null,
													expandChunk: null,
													preview: null
												};
											}}
											class="flex items-center gap-2 px-4 text-sm text-[#667085] transition-colors hover:text-[#344054]"
										>
											<!-- {@render assistantIcon('h-4 w-4')} -->

											{#if threadItem.reasoning_time}
												Thought for {threadItem.reasoning_time.toFixed()} second{Number(
													threadItem.reasoning_time.toFixed()
												) > 1
													? 's'
													: ''}
											{:else}
												Reasoning
											{/if}

											<ChevronRight size={16} />
										</button>
									{/if}

									<div
										data-testid="chat-message"
										class:w-full={multiturnCols.length > 1}
										class="group relative max-w-full scroll-my-2 self-start rounded-xl bg-[#F2F4F7] p-4 text-text data-dark:bg-[#5B7EE5]"
									>
										{#if isEditingCell}
											<!-- {@render cellContentEditor(threadItem)} -->
										{:else if typeof threadItem.content === 'string'}
											<p class="response-message flex flex-col gap-4 whitespace-pre-line text-sm">
												{#if !generationStatus?.includes(threadItem.row_id)}
													{#if showRawTexts}
														{threadItem.content}
													{:else}
														{@html converter
															.makeHtml(threadItem.content)
															.replaceAll(chatCitationPattern, (match, word) =>
																citationReplacer(
																	match,
																	word,
																	column,
																	threadItem.row_id,
																	(
																		threadItem.references ??
																		tableThread[column]?.thread?.find(
																			(item) => item.row_id === threadItem.row_id && item.references
																		)?.references
																	)?.chunks ?? []
																)
															)}
													{/if}
												{:else}
													{@html converter
														.makeHtml(loadedStreams[threadItem.row_id]?.[column]?.join('') ?? '')
														.replaceAll(chatCitationPattern, (match, word) =>
															citationReplacer(
																match,
																word,
																column,
																threadItem.row_id,
																loadedReferences?.[threadItem.row_id]?.[column].chunks ?? []
															)
														)}
												{/if}
											</p>
										{:else}
											{@const textContent = threadItem.content
												.filter((c) => c.type === 'text')
												.map((c) => c.text)
												.join('')}
											<!-- TODO: Insert images/file -->
											<p class="response-message flex flex-col gap-4 whitespace-pre-line text-sm">
												{#if !generationStatus?.includes(threadItem.row_id)}
													{#if showRawTexts}
														{textContent}
													{:else}
														{@html converter
															.makeHtml(textContent)
															.replaceAll(chatCitationPattern, (match, word) =>
																citationReplacer(
																	match,
																	word,
																	column,
																	threadItem.row_id,
																	(
																		threadItem.references ??
																		tableThread[column]?.thread?.find(
																			(item) => item.row_id === threadItem.row_id && item.references
																		)?.references
																	)?.chunks ?? []
																)
															)}
													{/if}
												{:else}
													{@html converter
														.makeHtml(loadedStreams[threadItem.row_id]?.[column]?.join('') ?? '')
														.replaceAll(chatCitationPattern, (match, word) =>
															citationReplacer(
																match,
																word,
																column,
																threadItem.row_id,
																loadedReferences?.[threadItem.row_id]?.[column].chunks ?? []
															)
														)}
												{/if}
											</p>
										{/if}
									</div>
								</div>
							{/if}
						{/if}
					{/each}
				</div>
			{/if}
		{/each}
	{:else}
		<div class="absolute bottom-0 left-0 right-0 top-0 flex items-center justify-center">
			<LoadingSpinner class="h-6 text-secondary" />
		</div>
	{/if}
</div>

<div
	style="grid-template-rows: minmax(0, auto);"
	class="mx-auto grid w-full max-w-6xl px-2.5 transition-[grid-template-rows,padding] duration-300"
>
	<div
		style="grid-template-columns: auto;"
		class="grid w-full items-end gap-2 pb-3 transition-[background-color,grid-template-columns] duration-300 @container @2xl/chat:pb-4"
	>
		<div
			style="box-shadow: 0px 4px 12px 0px rgba(0, 0, 0, 0.06);"
			class="relative mt-2 flex w-full flex-col items-start gap-2 rounded-xl border border-[#E4E7EC] bg-white px-4 py-3 text-text transition-colors data-dark:border-[#666] data-dark:bg-[#303338]"
		>
			<button
				tabindex="-1"
				title="Drag to resize chat area"
				aria-label="Drag to resize chat area"
				onmousedown={() => (isResizing = true)}
				class="group absolute -top-[4px] left-0 right-0 mx-6 h-[10px] cursor-ns-resize focus:outline-none"
			>
				<div
					class="absolute top-[4px] h-[1px] w-full rounded-md bg-black opacity-0 group-hover:opacity-100 data-dark:bg-white {isResizing &&
						'opacity-100'} transition-opacity"
				></div>
			</button>

			{#if Object.keys(uploadColumns).length > 0}
				<div class="flex flex-wrap gap-2">
					{#each Object.entries(uploadColumns) as [uploadColumn, { uri }]}
						{@const fileType = fileColumnFiletypes.find(({ ext }) =>
							uri.toLowerCase().endsWith(ext)
						)?.type}
						{@const fileUrl = rowThumbs[uri]}
						<div class="group/image relative">
							<button
								title={uri.split('/').pop()}
								onclick={() => (showFilePreview = uri)}
								class:pointer-events-none={uri === 'loading'}
								class="flex h-16 w-16 items-center justify-center overflow-hidden rounded-xl bg-[#BF416E]"
							>
								{#if uri === 'loading'}
									<LoadingSpinner class="m-0 h-5 w-5 text-white" />
								{:else if fileUrl}
									{#if fileType === 'image'}
										<img src={fileUrl} alt="" class="z-0 h-full w-full object-cover" />
									{:else if fileType === 'audio'}
										<AudioLines class="h-16 w-16 text-white" />
									{:else if fileType === 'document'}
										<img src={fileUrl} alt="" class="z-0 h-full w-full object-cover" />
									{/if}
								{/if}
							</button>

							<button
								title="Delete file"
								onclick={() => delete uploadColumns[uploadColumn]}
								class="absolute right-0 top-0 z-10 -translate-y-[30%] translate-x-[30%] rounded-full bg-black p-0.5 opacity-0 transition-[opacity,background-color] hover:bg-neutral-600 group-hover/image:opacity-100"
							>
								<CloseIcon class="h-4 w-4 text-white" />
							</button>
						</div>
					{/each}
				</div>
			{/if}

			<form bind:this={chatForm} onsubmit={handleChatSubmit} class="flex w-full gap-1">
				<!-- svelte-ignore a11y_autofocus -->
				<textarea
					autofocus
					name="chatbar"
					placeholder="Enter message"
					bind:this={chat}
					bind:value={chatMessage}
					oninput={resizeChat}
					onkeydown={interceptSubmit}
					onpaste={(e) => {
						if (e.clipboardData?.items) {
							handleSelectFiles(
								[...e.clipboardData.items]
									.map((item) => {
										if (item.kind === 'file') {
											const itemFile = item.getAsFile();
											if (itemFile) {
												return itemFile;
											} else {
												return [];
											}
										} else {
											return [];
										}
									})
									.flat()
							);
						} else {
							handleSelectFiles([...(e.clipboardData?.files ?? [])]);
						}
					}}
					class="h-12 min-h-[48px] w-full resize-none bg-transparent outline-none placeholder:text-[#98A2B3]"
				></textarea>

				<Button
					title="Send message"
					onclick={() => {
						isResized = false;
						chatForm?.requestSubmit();
					}}
					disabled={(!chatMessage && Object.values(uploadColumns).every((col) => !col.uri)) ||
						!!generationStatus}
					class="h-9 w-9 flex-[0_0_auto] rounded-full p-0"
				>
					<ArrowUp class="h-7" />
				</Button>
			</form>

			<div class="flex justify-between">
				{#if fileColumns.length > 0 && Object.keys(uploadColumns).length < fileColumns.length}
					<Button
						variant="action"
						size="sm"
						onclick={(e) => {
							e.currentTarget.querySelector('input')?.click();
						}}
						class="gap-2 px-2 font-normal text-[#344054]"
					>
						<ArrowDownToLine class="h-4 w-4 rotate-180 stroke-[1.5]" />
						Upload file or image

						<input
							type="file"
							accept={fileColumnFiletypes
								.filter(({ type }) =>
									fileColumns
										.filter((c) => !uploadColumns[c.id]?.uri?.trim())
										.map((c) => c.dtype)
										.includes(type)
								)
								.map(({ ext }) => ext)
								.join(',')}
							onchange={(e) => {
								e.preventDefault();
								handleSelectFiles([...(e.currentTarget.files ?? [])]);
							}}
							multiple={false}
							class="fixed max-h-[0] max-w-0 overflow-hidden !border-none !p-0"
						/>
					</Button>
				{/if}

				<p></p>
			</div>
		</div>

		<!-- <div
			class="relative mt-2 flex w-full items-center rounded-[1.8rem] border border-[#E4E7EC] bg-white p-1 text-text transition-colors has-[textarea:focus]:border-[#d5607c] has-[textarea:focus]:shadow-[0_0_0_1px_#FFD8DF] data-dark:border-[#666] data-dark:bg-[#303338]"
		>
			<button
				tabindex="-1"
				title="Drag to resize chat area"
				aria-label="Drag to resize chat area"
				onmousedown={() => (isResizing = true)}
				class="group absolute -top-[4px] left-0 right-0 mx-6 h-[10px] cursor-ns-resize focus:outline-none"
			>
				<div
					class="absolute top-[4px] h-[1px] w-full rounded-md bg-black opacity-0 group-hover:opacity-100 data-dark:bg-white {isResizing &&
						'opacity-100'} transition-opacity"
				></div>
			</button>

			<form bind:this={chatForm} onsubmit={handleChatSubmit} class="flex w-full">
				<!-- svelte-ignore a11y_autofocus ->
				<textarea
					autofocus
					name="chatbar"
					placeholder="Enter message"
					bind:this={chat}
					bind:value={chatMessage}
					oninput={resizeChat}
					onkeydown={interceptSubmit}
					class="h-12 min-h-[48px] w-full resize-none bg-transparent p-3 pl-5 outline-none placeholder:text-[#999999]"
				></textarea>
			</form>

			<Button
				variant="ghost"
				title="Send message"
				onclick={() => {
					isResized = false;
					chatForm?.requestSubmit();
				}}
				class="h-12 rounded-full {chatMessage
					? 'fill-black data-dark:fill-white'
					: 'pointer-events-none fill-[#999999]'}"
			>
				<SendIcon class="h-7" />
			</Button>
		</div> -->
	</div>
</div>

<!-- <div class="flex items-center justify-center sm:mx-24 my-0 h-full">
			<span class="relative -top-[0.05rem] text-3xl font-extralight">
				{threadError.error}
			</span>
			<div
				class="flex items-center ml-4 pl-4 min-h-10 border-l border-[#ccc] data-dark:border-[#666]"
			>
				<h1>{JSON.stringify(threadError.message)}</h1>
			</div>
		</div> -->

<ChatFilePreview bind:showFilePreview />
<ChatThumbsFetch {uris} bind:rowThumbs />

<style>
	.message-container::-webkit-scrollbar {
		width: 6px;
		height: 0px;
		border: 0px solid hsl(0, 0%, 27%);
		border-top: 0;
		border-bottom: 0;
	}

	.message-container {
		grid-auto-flow: column;
		grid-auto-columns: 100%;
	}

	@container chat (min-width: 1024px) {
		.message-container {
			grid-auto-columns: 50%;
		}
	}

	@supports not (container-type: inline-size) {
		@media (min-width: 1280px) {
			.message-container {
				grid-auto-columns: 50%;
			}
		}
	}
</style>
