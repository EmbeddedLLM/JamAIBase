<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount, tick } from 'svelte';
	import { v4 as uuidv4 } from 'uuid';
	import { ArrowDownToLine, AudioLines } from '@lucide/svelte';
	import { browser } from '$app/environment';
	import { page } from '$app/state';
	import showdown from 'showdown';
	//@ts-expect-error - no types
	import showdownHtmlEscape from 'showdown-htmlescape';
	import '../../../../../../showdown-theme.css';
	import { getTableState } from '$lib/components/tables/tablesState.svelte';
	import { codeblock, codehighlight, table as tableExtension } from '$lib/showdown';
	import { fileColumnFiletypes } from '$lib/constants';
	import { cn } from '$lib/utils';
	import logger from '$lib/logger';
	import type {
		ChatReferences,
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

	const tableState = getTableState();

	interface Props {
		tableData: GenTable | undefined;
		tableThread: ChatThreads['threads'];
		threadLoaded: boolean;
		generationStatus: string | null;
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

	const converter = new showdown.Converter({
		tables: true,
		tasklists: true,
		disableForced4SpacesIndentedSublists: true,
		strikethrough: true,
		ghCompatibleHeaderId: true,
		extensions: [showdownHtmlEscape, codeblock, codehighlight, tableExtension]
	});

	let loadedStreams: Record<string, string[]> = $state({});
	let latestStreams: Record<string, string> = $state({});

	let showRawTexts = $state(false);

	let chatWindow: HTMLDivElement | null = $state(null);
	let isLoading = true;

	//Chatbar
	let chatForm: HTMLFormElement | null = $state(null);
	let chat: HTMLTextAreaElement | null = $state(null);

	let chatMessage = $state('');
	let isResizing = $state(false);
	let isResized = $state(false);

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
	let displayedLoadedStreams = $derived(
		Object.keys(loadedStreams).filter((colID) => {
			// Filter out columns to display
			const col = tableData?.cols?.find((col) => col.id === colID);
			return col?.gen_config?.object === 'gen_config.llm' && col.gen_config.multi_turn;
		})
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
		chatMessage = '';

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
								}
							],
							name: null,
							user_prompt: cachedPrompt,
							references: null
						}
					]
				}
			])
		);

		generationStatus = 'new';
		loadedStreams = Object.fromEntries(
			tableData.cols
				.map((col) =>
					col.gen_config?.object === 'gen_config.llm' && col.gen_config.multi_turn
						? [[col.id, []]]
						: []
				)
				.flat()
		);
		latestStreams = Object.fromEntries(
			tableData.cols
				.map((col) =>
					col.gen_config?.object === 'gen_config.llm' && col.gen_config.multi_turn
						? [[col.id, '']]
						: []
				)
				.flat()
		);

		//? Show user message
		await tick();
		chatWindow.scrollTop = chatWindow.scrollHeight;

		//? Send message to the server
		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/gen_tables/chat/rows/add`, {
			method: 'POST',
			headers: {
				Accept: 'text/event-stream',
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id
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
			const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();

			let row_id = '';
			let references: Record<string, ChatReferences> | null = null;
			let buffer = '';
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
										row_id = parsedEvent.data.row_id;

										if (loadedStreams[parsedEvent.data.output_column_name]) {
											if ((parsedEvent.data.choices[0].message.content ?? '').includes('\n')) {
												loadedStreams[parsedEvent.data.output_column_name] = [
													...loadedStreams[parsedEvent.data.output_column_name],
													latestStreams[parsedEvent.data.output_column_name] +
														(parsedEvent.data.choices[0]?.message?.content ?? '')
												];
												latestStreams[parsedEvent.data.output_column_name] = '';
											} else {
												latestStreams[parsedEvent.data.output_column_name] +=
													parsedEvent.data.choices[0]?.message?.content ?? '';
											}
										}

										scrollToBotttom();
									}
								} else if (parsedEvent.data.object === 'gen_table.references') {
									references = {
										...(references ?? {}),
										[parsedEvent.data.output_column_name]:
											parsedEvent.data as unknown as ChatReferences
									};
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

			loadedStreams = Object.fromEntries(
				Object.entries(loadedStreams).map(([col, streams]) => [
					col,
					[...streams, latestStreams[col]]
				])
			);

			tableThread = Object.fromEntries(
				Object.entries(tableThread).map(([outCol, thread]) => {
					const loadedStreamCol = loadedStreams[outCol];
					const colReferences = references?.[outCol] ?? null;
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
			loadedStreams = {};
			latestStreams = {};
			generationStatus = null;

			refetchTable();
		}
	}

	onMount(() => {
		if (chatWindow) chatWindow.scrollTop = chatWindow.scrollHeight;
	});

	const scrollToBotttom = async () => {
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
		scrollToBotttom();
	});

	function handleResize(e: MouseEvent) {
		if (!chat) return;
		if (!isResizing) return;

		const chatBottomSpace = 24;
		const chatbarMaxHeight = window.innerHeight * 0.65;
		const chatbarHeight = window.innerHeight - e.clientY - chatBottomSpace - 8;

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
	class="relative flex grow flex-col gap-4 overflow-y-auto overflow-x-hidden pt-6 [scrollbar-gutter:stable]"
>
	{#if threadLoaded}
		{@const multiturnCols = Object.keys(tableThread)}
		{@const longestThreadColLen = tableThread[longestThreadCol]?.thread?.length ?? 0}
		{#each Array(longestThreadColLen).fill('') as _, index}
			<div
				class="group/message-container message-container flex flex-[0_0_auto] gap-3 px-3 transition-[padding] @2xl/chat:px-6 @4xl/chat:px-20 @6xl/chat:px-36 @7xl/chat:px-72 supports-[not(container-type:inline-size)]:px-6 supports-[not(container-type:inline-size)]:lg:px-20 supports-[not(container-type:inline-size)]:2xl:px-36 supports-[not(container-type:inline-size)]:3xl:px-72"
			>
				{#each Object.entries(tableThread) as [column, thread]}
					{@const threadItem = thread.thread[index]}
					{#if threadItem && threadItem.role !== 'system'}
						{#if threadItem.role === 'user'}
							{@const isEditingCell = false}
							<div
								data-role="user"
								class={cn(
									'ml-auto flex flex-col gap-1 transition-[padding]',
									multiturnCols.length > 1
										? 'min-w-full @5xl/chat:min-w-[50%] supports-[not(container-type:inline-size)]:xl:min-w-[50%]'
										: '',
									multiturnCols.length == 1
										? '@5xl/chat:pl-[20%] supports-[not(container-type:inline-size)]:xl:pl-[20%]'
										: 'last:pr-3 @2xl/chat:last:pr-6 @4xl/chat:last:pr-20 @5xl/chat:last:pr-0 supports-[not(container-type:inline-size)]:last:pr-6 supports-[not(container-type:inline-size)]:lg:last:pr-20 supports-[not(container-type:inline-size)]:xl:last:pr-0'
								)}
							>
								<div class="flex items-end justify-end">
									<!-- <div
												class:invisible={isEditingCell}
												class="flex items-center opacity-0 transition-opacity group-hover/message-container:opacity-100"
											>
												<Button
													variant="ghost"
													title="Edit content"
													onclick={async () => {
														chatState.editingContent = {
															rowID: threadItem.row_id,
															columnID: 'User'
														};
														await tick();
														resizeEditContent();
													}}
													class="h-7 w-7 p-0 text-[#98A2B3]"
												>
													<EditIcon class="h-3.5 w-3.5" />
												</Button>
											</div> -->
								</div>

								<div
									data-testid="chat-message"
									class:w-full={multiturnCols.length > 1}
									class="group relative flex max-w-full scroll-my-2 flex-col gap-2 self-end rounded-xl bg-white p-4 data-dark:bg-[#444]"
								>
									{#if isEditingCell}
										<!-- {@render cellContentEditor(
													threadItem.user_prompt ?? ''
													// typeof threadItem.content === 'string'
													// 	? threadItem.content
													// 	: threadItem.content.find((c) => c.type === 'text')?.text ?? ''
												)} -->
									{:else if typeof threadItem.content === 'string'}
										<div
											class="whitespace-pre-wrap text-sm [overflow-wrap:anywhere] focus:outline-none"
										>
											{threadItem.user_prompt}
										</div>
									{:else}
										{#if threadItem.content.some((c) => c.type === 'input_s3')}
											<div class="flex flex-wrap gap-2">
												{#each threadItem.content as content}
													{#if content.type === 'input_s3'}
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
																{#if fileType === 'image'}
																	<img
																		src={fileUrl}
																		alt=""
																		class="z-0 h-full w-full object-cover"
																	/>
																{:else if fileType === 'audio'}
																	<AudioLines class="h-16 w-16 text-white" />
																{:else if fileType === 'document'}
																	<img src={fileUrl} alt="" class="z-0 max-w-full object-contain" />
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
												{/each}
											</div>
										{/if}

										<p
											class="whitespace-pre-wrap text-sm [overflow-wrap:anywhere] focus:outline-none"
										>
											{threadItem.user_prompt}
										</p>
									{/if}
								</div>

								<!-- {#if isEditingCell}
											{@render cellContentEditorControls()}
										{/if} -->
							</div>
						{:else if threadItem.role === 'assistant'}
							{@const isEditingCell = false}
							<div
								data-role="assistant"
								class={cn(
									'group/message-container flex flex-col gap-1 transition-[padding]',
									multiturnCols.length > 1
										? 'min-w-full @5xl/chat:min-w-[50%] supports-[not(container-type:inline-size)]:xl:min-w-[50%]'
										: '',
									multiturnCols.length == 1
										? '@5xl/chat:pr-[20%] supports-[not(container-type:inline-size)]:xl:pr-[20%]'
										: 'last:pr-3 @2xl/chat:last:pr-6 @4xl/chat:last:pr-20 @5xl/chat:last:pr-0 supports-[not(container-type:inline-size)]:last:pr-6 supports-[not(container-type:inline-size)]:lg:last:pr-20 supports-[not(container-type:inline-size)]:xl:last:pr-0'
								)}
							>
								{#if threadItem.row_id !== generationStatus}
									<div class="flex items-end justify-between">
										<div class="flex items-center gap-2 text-sm">
											<span class="line-clamp-1 text-[#98A2B3]">
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
													chatState.editingContent = {
														rowID: threadItem.row_id,
														columnID: column
													};
													await tick();
													resizeEditContent();
												}}
												class="h-7 w-7 p-0 text-[#98A2B3]"
											>
												<EditIcon class="h-3.5 w-3.5" />
											</Button>

											<Button
												variant="ghost"
												title="Regenerate message"
												onclick={() => chatState.regenMessage(threadItem.row_id)}
												class="h-7 w-7 p-0 text-[#98A2B3]"
											>
												<RegenerateIcon class="h-6 w-6" />
											</Button>

											{#if threadItem.references}
												<Button
													variant="ghost"
													title="Show references"
													onclick={() =>
														(showReferences = {
															open: true,
															message: {
																columnID: column,
																threadItem
															},
															preview: null
														})}
													class="h-7 w-7 p-0 text-[#98A2B3]"
												>
													<FileText class="h-4 w-4" />
												</Button>
											{/if} -->
										</div>
									</div>

									<div
										data-testid="chat-message"
										class:w-full={multiturnCols.length > 1}
										class="group relative max-w-full scroll-my-2 self-start rounded-xl bg-[#F2F4F7] p-4 text-text data-dark:bg-[#5B7EE5]"
									>
										{#if isEditingCell}
											<!-- {@render cellContentEditor(
												typeof threadItem.content === 'string'
													? threadItem.content
													: threadItem.content.find((c) => c.type === 'text')?.text ?? ''
											)} -->
										{:else if typeof threadItem.content === 'string'}
											<p class="response-message flex flex-col gap-4 whitespace-pre-line text-sm">
												{#if showRawTexts}
													{threadItem.content}
												{:else}
													{@const rawHtml = converter.makeHtml(threadItem.content)}
													{@html rawHtml}
												{/if}
											</p>
										{:else}
											{@const textContent = threadItem.content
												.filter((c) => c.type === 'text')
												.map((c) => c.text)
												.join('')}
											<!-- TODO: Insert images/file -->
											<p class="response-message flex flex-col gap-4 whitespace-pre-line text-sm">
												{#if showRawTexts}
													{textContent}
												{:else}
													{@const rawHtml = converter.makeHtml(textContent)}
													{@html rawHtml}
												{/if}
											</p>
										{/if}
									</div>

									{#if isEditingCell}
										<!-- {@render cellContentEditorControls()} -->
									{/if}
								{:else}
									{@render generatingMessages(column)}
								{/if}
							</div>
						{/if}
					{/if}
				{/each}
			</div>
		{/each}

		{#if generationStatus === 'new'}
			{@render generatingMessages()}
		{/if}
	{:else}
		<div class="absolute bottom-0 left-0 right-0 top-0 flex items-center justify-center">
			<LoadingSpinner class="h-6 text-secondary" />
		</div>
	{/if}
</div>

<div
	style="grid-template-rows: minmax(0, auto);"
	class="grid px-3 transition-[grid-template-rows,padding] duration-300 @2xl/chat:px-6 @4xl/chat:px-20 @6xl/chat:px-36 @7xl/chat:px-72 supports-[not(container-type:inline-size)]:px-6 supports-[not(container-type:inline-size)]:lg:px-20 supports-[not(container-type:inline-size)]:2xl:px-36 supports-[not(container-type:inline-size)]:3xl:px-72"
>
	<div
		style="grid-template-columns: auto;"
		class="grid w-full items-end gap-2 pb-3 transition-[background-color,grid-template-columns] duration-300 @container @2xl/chat:pb-6"
	>
		<div
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
				<!-- svelte-ignore a11y_autofocus -->
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
		</div>
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

{#snippet generatingMessages(columnID?: string)}
	{#if columnID}
		{#each displayedLoadedStreams as key}
			{#if key === columnID}
				{@const loadedStream = loadedStreams[key]}
				{@const latestStream = latestStreams[key] ?? ''}
				<div class="flex items-center gap-2 text-sm">
					<span class="line-clamp-1 text-[#98A2B3]">
						{key}
					</span>
				</div>

				<div
					data-testid="chat-message"
					data-streaming="true"
					class:w-full={displayedLoadedStreams.length > 1}
					class="group relative max-w-full scroll-my-2 self-start rounded-xl bg-[#F2F4F7] p-4 text-text data-dark:bg-[#5B7EE5]"
				>
					<p class="response-message flex flex-col gap-4 whitespace-pre-line text-sm">
						{@html converter.makeHtml(loadedStream.join(''))}
						{latestStream}

						{#if loadedStream.length === 0 && latestStream === ''}
							<RowStreamIndicator />
						{/if}
					</p>
				</div>
			{/if}
		{/each}
	{:else}
		<div
			class="message-container flex flex-[0_0_auto] gap-3 overflow-x-auto overflow-y-hidden px-3 transition-[padding] @2xl/chat:px-6 @4xl/chat:px-20 @6xl/chat:px-36 @7xl/chat:px-72 supports-[not(container-type:inline-size)]:px-6 supports-[not(container-type:inline-size)]:lg:px-20 supports-[not(container-type:inline-size)]:2xl:px-36 supports-[not(container-type:inline-size)]:3xl:px-72"
		>
			{#each displayedLoadedStreams as key}
				{@const loadedStream = loadedStreams[key]}
				{@const latestStream = latestStreams[key] ?? ''}
				<div
					class={cn(
						'group/message-container flex flex-col gap-1',
						displayedLoadedStreams.length > 1
							? 'min-w-full @5xl/chat:min-w-[50%] supports-[not(container-type:inline-size)]:xl:min-w-[50%]'
							: '',
						displayedLoadedStreams.length == 1
							? '@5xl/chat:pr-[20%] supports-[not(container-type:inline-size)]:xl:pr-[20%]'
							: ''
					)}
				>
					<div class="flex items-center gap-2 text-sm">
						<span class="line-clamp-1 text-[#98A2B3]">
							{key}
						</span>
					</div>

					<div
						data-testid="chat-message"
						data-streaming="true"
						class:w-full={displayedLoadedStreams.length > 1}
						class="group relative max-w-full scroll-my-2 self-start rounded-xl bg-[#F2F4F7] p-4 text-text data-dark:bg-[#5B7EE5]"
					>
						<p class="response-message flex flex-col gap-4 whitespace-pre-line text-sm">
							{@html converter.makeHtml(loadedStream.join(''))}
							{latestStream}

							{#if loadedStream.length === 0 && latestStream === ''}
								<RowStreamIndicator />
							{/if}
						</p>
					</div>
				</div>
			{/each}
		</div>
	{/if}
{/snippet}

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
