<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount, tick } from 'svelte';
	import { browser } from '$app/environment';
	import { page } from '$app/stores';
	import showdown from 'showdown';
	//@ts-expect-error - no types
	import showdownHtmlEscape from 'showdown-htmlescape';
	import '../../../../../../showdown-theme.css';
	import logger from '$lib/logger';
	import { codeblock, codehighlight, table as tableExtension } from '$lib/showdown';
	import type { GenTable, GenTableCol, GenTableStreamEvent, Thread } from '$lib/types';

	import RowStreamIndicator from '$lib/components/preset/RowStreamIndicator.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import SendIcon from '$lib/icons/SendIcon.svelte';
	import RegenerateIcon from '$lib/icons/RegenerateIcon.svelte';
	import MultiturnChatIcon from '$lib/icons/MultiturnChatIcon.svelte';
	import TuneIcon from '$lib/icons/TuneIcon.svelte';

	export let tableData: GenTable | undefined;
	export let thread: Thread[][];
	export let threadLoaded: boolean;
	export let generationStatus: boolean;
	export let isColumnSettingsOpen: { column: GenTableCol | null; showMenu: boolean };
	export let refetchTable: (hideColumnSettings?: boolean) => Promise<void>;

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

	let loadedStreams: Record<string, string[]> = {};
	let latestStreams: Record<string, string> = {};

	let showRawTexts = false;

	let chatWindow: HTMLDivElement;
	let isLoading = true;

	//Chatbar
	let chatForm: HTMLFormElement;
	let chat: HTMLTextAreaElement;

	let chatMessage = '';
	let isResizing = false;
	let isResized = false;

	function resizeChat() {
		if (isResized) return; //? Prevents textarea from resizing by typing when chatbar is resized by user
		chat.style.height = '3rem';
		chat.style.height = (chat.scrollHeight >= 180 ? 180 : chat.scrollHeight) + 'px';
	}

	function interceptSubmit(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			isResized = false;
			chatForm.requestSubmit();
		}
	}

	async function handleChatSubmit() {
		if (!tableData || !thread) return;
		if (generationStatus || !chatMessage.trim()) return;
		const cachedChatMessage = chatMessage;
		chatMessage = '';

		// chatMessage = '';
		chat.style.height = '3rem';

		//? Add user message to the chat
		thread = [
			...thread,
			[
				{
					column_id: '',
					role: 'user',
					content: cachedChatMessage
				}
			]
		];

		// generationStatus = true;
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
		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/rows/add`, {
			method: 'POST',
			headers: {
				Accept: 'text/event-stream',
				'Content-Type': 'application/json',
				'x-project-id': $page.params.project_id
			},
			body: JSON.stringify({
				table_id: $page.params.table_id,
				data: [
					{
						User: cachedChatMessage
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
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
			thread = thread.slice(0, -1);
			chatMessage = cachedChatMessage;
		} else {
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
								logger.error('CHATTBL_CHAT_ADDSTREAMPARSE', { parsing: sumValue, error: err });
								continue;
							}

							if (parsedValue.object == 'gen_table.completion.chunk') {
								if (parsedValue.choices[0].finish_reason) {
									switch (parsedValue.choices[0].finish_reason) {
										case 'error': {
											logger.error('CHATTBL_CHAT_ADDSTREAM', parsedValue);
											console.error('STREAMING_ERROR', parsedValue);
											alert(`Error while streaming: ${parsedValue.choices[0].message.content}`);
											break;
										}
									}
								} else {
									if ((parsedValue.choices[0].message.content ?? '').includes('\n')) {
										loadedStreams[parsedValue.output_column_name] = [
											...loadedStreams[parsedValue.output_column_name],
											latestStreams[parsedValue.output_column_name] +
												(parsedValue.choices[0]?.message?.content ?? '')
										];
										latestStreams[parsedValue.output_column_name] = '';
									} else {
										latestStreams[parsedValue.output_column_name] +=
											parsedValue.choices[0]?.message?.content ?? '';
									}
								}
							} else {
								console.warn('Unknown message:', parsedValue);
							}
						}
					} else {
						lastMessage += value;
					}
				} catch (err) {
					logger.error('CHATTBL_ROW_ADDSTREAM', err);
					console.error(err);
					break;
				}
			}

			thread = [
				...thread,
				Object.keys(loadedStreams).map((key) => ({
					column_id: key,
					role: 'assistant',
					content: [...loadedStreams[key], latestStreams[key]].join('')
				}))
			];
			loadedStreams = {};
			latestStreams = {};

			refetchTable();
		}

		generationStatus = false;
	}

	onMount(() => {
		chatWindow.scrollTop = chatWindow.scrollHeight;
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
	$: loadedStreams, scrollToBotttom();

	function handleResize(e: MouseEvent) {
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
</script>

<svelte:document
	on:mousemove={handleResize}
	on:mouseup={() => (isResizing = false)}
	on:click={handleCustomBtnClick}
	on:keydown={(e) => {
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
	class="relative grow flex flex-col gap-4 pt-6 pb-16 overflow-x-hidden overflow-y-auto [scrollbar-gutter:stable]"
>
	{#if threadLoaded}
		{#each thread as threadItem, index}
			{@const nonErrorMessage = threadItem.find((v) => 'content' in v && v.role === 'user')}
			{@const messages = nonErrorMessage ? [nonErrorMessage] : threadItem}
			{@const messagesWithContent = messages.filter(
				(v) => ('content' in v && v.content?.trim()) || 'error' in v
			)}
			<div
				style="--message-len: {messagesWithContent.length};"
				class="flex-[0_0_auto] grid message-container gap-3 px-6 lg:px-20 2xl:px-36 3xl:px-72 overflow-x-auto overflow-y-hidden"
			>
				{#each messages as message}
					{@const { column_id } = message}
					{#if 'content' in message}
						{@const { content, role } = message}
						{#if content?.trim()}
							{#if role == 'assistant'}
								<div
									class="flex flex-col gap-1 {messagesWithContent.length === 1
										? 'col-span-1 xl:col-span-2'
										: ''} group/message-container"
								>
									<div class="flex items-center justify-between">
										<button
											on:click={() => {
												const targetCol = tableData?.cols?.find((col) => col.id == column_id);
												if (targetCol) {
													isColumnSettingsOpen = { column: targetCol, showMenu: true };
												}
											}}
											class="flex items-center gap-2 text-sm"
										>
											<span
												style="background-color: #FFEAD5; color: #FD853A;"
												class="w-min p-0.5 py-1 whitespace-nowrap rounded-[0.1875rem] select-none flex items-center"
											>
												<span class="capitalize text-xs font-medium px-1"> output </span>
												<span
													class="bg-white w-min px-1 text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
												>
													str
												</span>

												<hr class="ml-1 h-3 border-l border-[#FD853A]" />
												<div class="relative h-4 w-[18px]">
													<MultiturnChatIcon class="absolute h-[18px] -translate-y-px" />
												</div>
											</span>

											<span class="line-clamp-2">
												{column_id}
											</span>
										</button>
									</div>

									<div
										data-testid="chat-message"
										class="relative self-start {messagesWithContent.length === 1
											? 'xl:mr-[20%]'
											: 'w-full'} p-4 max-w-full rounded-xl bg-[#F2F4F7] data-dark:bg-[#5B7EE5] text-text group scroll-my-2"
									>
										<p
											class="flex-col gap-4 response-message whitespace-pre-line text-sm {generationStatus &&
											index === thread.length - 1 &&
											content.length !== 0
												? 'block response-cursor'
												: 'flex'}"
										>
											{#if showRawTexts}
												{message}
											{:else}
												{@const rawHtml = converter.makeHtml(content)}
												{@html rawHtml}
											{/if}
										</p>
									</div>
								</div>
							{:else if role == 'user'}
								<div
									class="flex flex-col gap-1 {messagesWithContent.length === 1
										? 'col-span-1 xl:col-span-2'
										: ''}"
								>
									<div
										data-testid="chat-message"
										class="relative self-end flex flex-col max-w-full lg:ml-[20%] rounded-xl bg-white data-dark:bg-[#444] group scroll-my-2"
									>
										<p
											class="p-4 text-sm [overflow-wrap:anywhere] focus:outline-none whitespace-pre-wrap"
										>
											{content}
										</p>
									</div>
								</div>
							{/if}
						{/if}
					{:else if messages.every((v) => ('content' in v && v.role === 'assistant') || 'error' in v)}
						<div
							class="flex flex-col gap-1 {messagesWithContent.length === 1
								? 'col-span-1 xl:col-span-2'
								: ''} group/message-container"
						>
							<div class="flex items-center justify-between">
								<button
									on:click={() => {
										const targetCol = tableData?.cols?.find((col) => col.id == column_id);
										if (targetCol) {
											isColumnSettingsOpen = { column: targetCol, showMenu: true };
										}
									}}
									class="flex items-center gap-2 text-sm"
								>
									<span
										style="background-color: #FFEAD5; color: #FD853A;"
										class="w-min p-0.5 py-1 whitespace-nowrap rounded-[0.1875rem] select-none flex items-center"
									>
										<span class="capitalize text-xs font-medium px-1"> output </span>
										<span
											class="bg-white w-min px-1 text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
										>
											str
										</span>

										<hr class="ml-1 h-3 border-l border-[#FD853A]" />
										<div class="relative h-4 w-[18px]">
											<MultiturnChatIcon class="absolute h-[18px] -translate-y-px" />
										</div>
									</span>

									<span class="line-clamp-2">
										{column_id}
									</span>
								</button>
							</div>

							<div
								data-testid="chat-message"
								class="relative self-start {messagesWithContent.length === 1
									? 'xl:mr-[20%]'
									: 'w-full'} p-4 w-full max-w-full rounded-xl bg-[#F2F4F7] data-dark:bg-[#5B7EE5] text-text group scroll-my-2"
							>
								<div class="flex items-center justify-center py-8 h-full">
									<span class="relative -top-[0.05rem] text-3xl font-extralight">
										{message.error}
									</span>
									<div
										class="flex items-center ml-4 pl-4 min-h-10 border-l border-[#ccc] data-dark:border-[#666]"
									>
										<h1 class="whitespace-pre-wrap">
											{message.message.message || JSON.stringify(message)}
										</h1>
									</div>
								</div>
							</div>
						</div>
					{:else}
						empty block
					{/if}
				{/each}
			</div>
		{/each}

		<div
			style="--message-len: {Object.keys(loadedStreams).length};"
			class="flex-[0_0_auto] grid message-container gap-3 px-6 lg:px-20 2xl:px-36 3xl:px-72 overflow-x-auto overflow-y-hidden"
		>
			{#each Object.keys(loadedStreams) as key}
				{@const loadedStream = loadedStreams[key]}
				{@const latestStream = latestStreams[key] ?? ''}
				<div
					class="flex flex-col gap-1 {Object.keys(loadedStreams).length === 1
						? 'col-span-1 xl:col-span-2'
						: ''}"
				>
					<div class="flex items-center gap-2 text-sm">
						<span
							style="background-color: #FFEAD5; color: #FD853A;"
							class="w-min p-0.5 py-1 whitespace-nowrap rounded-[0.1875rem] select-none flex items-center"
						>
							<span class="capitalize text-xs font-medium px-1"> output </span>
							<span
								class="bg-white w-min px-1 text-xs font-medium whitespace-nowrap rounded-[0.1875rem] select-none"
							>
								str
							</span>

							<hr class="ml-1 h-3 border-l border-[#FD853A]" />
							<div class="relative h-4 w-[18px]">
								<MultiturnChatIcon class="absolute h-[18px] -translate-y-px" />
							</div>
						</span>

						<span class="line-clamp-2">
							{key}
						</span>
					</div>

					<div
						data-testid="chat-message"
						data-streaming="true"
						class="relative self-start {Object.keys(loadedStreams).length === 1
							? 'xl:mr-[20%]'
							: 'w-full'} p-4 max-w-full rounded-xl bg-[#F2F4F7] data-dark:bg-[#5B7EE5] text-text group scroll-my-2"
					>
						<p
							class="flex-col gap-4 response-message whitespace-pre-line text-sm {loadedStream.length ||
							latestStream
								? 'block response-cursor'
								: 'flex'}"
						>
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
	{:else}
		<div class="absolute top-0 bottom-0 left-0 right-0 flex items-center justify-center">
			<LoadingSpinner class="h-6 text-secondary" />
		</div>
	{/if}
</div>

<div
	style="grid-template-rows: minmax(0, auto);"
	class="grid transition-[grid-template-rows] duration-300 px-6 lg:px-20 2xl:px-36 3xl:px-72"
>
	<div
		style="grid-template-columns: auto;"
		class="@container grid items-end gap-2 pb-6 w-full transition-[background-color,grid-template-columns] duration-300"
	>
		<div
			class="relative flex items-center mt-2 p-1 w-full bg-white data-dark:bg-[#303338] border border-[#E4E7EC] data-dark:border-[#666] has-[textarea:focus]:border-[#4169e1] rounded-[1.8rem] text-text transition-colors"
		>
			<button
				tabindex="-1"
				title="Drag to resize chat area"
				on:mousedown={() => (isResizing = true)}
				class="absolute -top-[4px] left-0 right-0 mx-6 h-[10px] cursor-ns-resize focus:outline-none group"
			>
				<div
					class="absolute top-[4px] h-[1px] w-full bg-black data-dark:bg-white rounded-md opacity-0 group-hover:opacity-100 {isResizing &&
						'opacity-100'} transition-opacity"
				/>
			</button>

			<form bind:this={chatForm} on:submit|preventDefault={handleChatSubmit} class="flex w-full">
				<!-- svelte-ignore a11y-autofocus -->
				<textarea
					autofocus
					name="chatbar"
					placeholder="Enter message"
					bind:this={chat}
					bind:value={chatMessage}
					on:input={resizeChat}
					on:keydown={interceptSubmit}
					class="p-3 pl-5 min-h-[48px] h-12 w-full bg-transparent resize-none outline-none placeholder:text-[#999999]"
				/>
			</form>

			<Button
				variant="ghost"
				title="Send message"
				on:click={() => {
					isResized = false;
					chatForm.requestSubmit();
				}}
				class="h-12 rounded-full {chatMessage
					? 'fill-black data-dark:fill-white'
					: 'fill-[#999999] pointer-events-none'}"
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

<style>
	:global(::-webkit-scrollbar) {
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

	@media (min-width: 1280px) {
		.message-container {
			grid-auto-columns: 50%;
		}
	}
</style>
