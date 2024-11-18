<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import { onMount, tick } from 'svelte';
	import { invalidate } from '$app/navigation';
	import { browser } from '$app/environment';
	import { page } from '$app/stores';
	import showdown from 'showdown';
	//@ts-expect-error - no types
	import showdownHtmlEscape from 'showdown-htmlescape';
	import '../../../../../../showdown-theme.css';
	import logger from '$lib/logger';
	import { codeblock, codehighlight, table as tableExtension } from '$lib/showdown';
	import type { ChatRequest, GenTableStreamEvent } from '$lib/types';

	import RowStreamIndicator from '$lib/components/preset/RowStreamIndicator.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import SendIcon from '$lib/icons/SendIcon.svelte';
	import RegenerateIcon from '$lib/icons/RegenerateIcon.svelte';

	// export let table: PageData['table'];
	export let thread: ChatRequest['messages'] | undefined;
	export let threadError: { error: number; message: any };
	export let generationStatus: boolean;

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

	let loadedStream: string[] = [];
	let latestStream = '';

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
		if (!thread) return;
		if (generationStatus || !chatMessage.trim()) return;
		const cachedChatMessage = chatMessage;
		chatMessage = '';

		// chatMessage = '';
		chat.style.height = '3rem';

		//? Add user message to the chat
		thread = [
			...thread,
			{
				role: 'user',
				content: cachedChatMessage
			}
		];

		generationStatus = true;

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
								if (
									parsedValue.choices[0].finish_reason &&
									parsedValue.choices[0].finish_reason === 'error'
								) {
									logger.error('CHATTBL_CHAT_ADDSTREAM', parsedValue);
									console.error('STREAMING_ERROR', parsedValue);
									alert(`Error while streaming: ${parsedValue.choices[0].message.content}`);
								} else if (parsedValue.output_column_name === 'AI') {
									if ((parsedValue.choices[0].message.content ?? '').includes('\n')) {
										loadedStream = [
											...loadedStream,
											latestStream + (parsedValue.choices[0]?.message?.content ?? '')
										];
										latestStream = '';
									} else {
										latestStream += parsedValue.choices[0]?.message?.content ?? '';
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
				{
					role: 'assistant',
					content: [...loadedStream, latestStream].join('')
				}
			];
			loadedStream = [];
			latestStream = '';

			invalidate('chat-table:slug');
		}

		generationStatus = false;
	}

	async function handleRegenerate() {
		if (!thread || thread.length === 0) return;
		if (thread.at(-1)?.role !== 'assistant') return;

		const cachedAssistantResponse = thread.at(-1)?.content ?? '';
		thread = thread.slice(0, -1);

		generationStatus = true;

		const rowsResponse = await fetch(
			`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/${$page.params.table_id}/rows?${new URLSearchParams(
				{
					offset: '0',
					limit: '1'
				}
			)}`,
			{
				headers: {
					'x-project-id': $page.params.project_id
				}
			}
		);
		const rowsBody = await rowsResponse.json();

		if (!rowsResponse.ok) {
			logger.error('CHATTBL_CHAT_REGENGETROW', rowsBody);
			console.error(rowsBody);
			return resetThread();
		}

		if (!rowsBody?.items?.length) {
			alert('No rows found');
			return resetThread();
		}

		const regenResponse = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/rows/regen`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': $page.params.project_id
			},
			body: JSON.stringify({
				table_id: $page.params.table_id,
				row_ids: [rowsBody.items[0].ID],
				stream: true
			})
		});

		if (regenResponse.status != 200) {
			const regenResponseBody = await regenResponse.json();
			logger.error('CHATTBL_CHAT_REGEN', regenResponseBody);
			toast.error('Failed to regenerate row', {
				id: regenResponseBody.message || JSON.stringify(regenResponseBody),
				description: CustomToastDesc,
				componentProps: {
					description: regenResponseBody.message || JSON.stringify(regenResponseBody),
					requestID: regenResponseBody.request_id
				}
			});
			resetThread();
		} else {
			const reader = regenResponse.body!.pipeThrough(new TextDecoderStream()).getReader();

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
								logger.error('CHATTBL_CHAT_REGENSTREAMPARSE', { parsing: sumValue, error: err });
								continue;
							}

							if (parsedValue.object == 'gen_table.completion.chunk') {
								if (
									parsedValue.choices[0].finish_reason &&
									parsedValue.choices[0].finish_reason === 'error'
								) {
									logger.error('CHATTBL_CHAT_REGENSTREAM', parsedValue);
									console.error('STREAMING_ERROR', parsedValue);
									alert(`Error while streaming: ${parsedValue.choices[0].message.content}`);
								} else if (parsedValue.output_column_name === 'AI') {
									if ((parsedValue.choices[0].message.content ?? '').includes('\n')) {
										loadedStream = [
											...loadedStream,
											latestStream + (parsedValue.choices[0]?.message?.content ?? '')
										];
										latestStream = '';
									} else {
										latestStream += parsedValue.choices[0]?.message?.content ?? '';
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
					logger.error('CHATTBL_ROW_REGENSTREAM', err);
					console.error(err);
					break;
				}
			}

			thread = [
				...thread,
				{
					role: 'assistant',
					content: [...loadedStream, latestStream].join('')
				}
			];
			loadedStream = [];
			latestStream = '';

			invalidate('chat-table:slug');
		}

		generationStatus = false;

		function resetThread() {
			thread = [
				...(thread ?? []),
				{
					role: 'assistant',
					content: cachedAssistantResponse
				}
			];
		}
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
	$: loadedStream, scrollToBotttom();

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
	class="relative grow flex flex-col gap-4 pt-6 pb-16 px-6 lg:px-20 2xl:px-36 3xl:px-72 overflow-x-hidden overflow-y-auto [scrollbar-gutter:stable]"
>
	{#if thread}
		{#each thread as threadItem, index}
			{@const { role, content: message } = threadItem}
			{#if role == 'assistant'}
				<div
					data-testid="chat-message"
					class="relative self-start xl:mr-[20%] p-4 max-w-full rounded-xl bg-[#F2F4F7] data-dark:bg-[#5B7EE5] text-text group scroll-my-2"
				>
					<p
						class="flex-col gap-4 response-message whitespace-pre-line text-sm {generationStatus &&
						index === thread.length - 1 &&
						message.length !== 0
							? 'block response-cursor'
							: 'flex'}"
					>
						{#if showRawTexts}
							{message}
						{:else}
							{@const rawHtml = converter.makeHtml(message)}
							{@html rawHtml}
							<!-- {#await addCitations(message_id, rawHtml, references)}
								{@html rawHtml}
							{:then promiseMessage}
								{@html promiseMessage}
							{/await} -->
						{/if}
					</p>

					<!-- {#if !generationStatus && index == thread.length - 1}
						<div
							class='absolute xl:top-3.5 top-[unset] xl:bottom-[unset] -bottom-9 xl:-right-9 right-[unset] xl:left-[unset] left-0'
						>
							<Button
								variant="ghost"
								on:click={() => showReferences(activeLineItem)}
								class="relative p-0 h-7 w-7 opacity-0 group-hover:opacity-100 fill-secondary-content rounded-[0.25rem] transition-opacity duration-75 group/btn"
							>
								<ReferencesIcon class="h-6 text-[#666] data-dark:text-white" />

								<Tooltip
									arrowSize={5}
									class="top-1/2 -translate-y-1/2 left-9 z-[100] flex flex-col py-1.5 gap-2 w-max text-xs whitespace-pre-line opacity-0 group-hover/btn:opacity-100 after:-left-2.5 after:bottom-1/2 after:translate-y-1/2 after:rotate-90 duration-75"
								>
									<span class="text-sm">References</span>
								</Tooltip>
							</Button>
						</div>
					{/if} -->
				</div>
			{:else if role == 'user'}
				<div
					data-testid="chat-message"
					class="relative self-end flex flex-col max-w-full lg:ml-[20%] rounded-xl bg-white data-dark:bg-[#444] group scroll-my-2"
				>
					<p class="p-4 text-sm [overflow-wrap:anywhere] focus:outline-none whitespace-pre-wrap">
						{message}
					</p>
				</div>
			{/if}
		{/each}

		{#if generationStatus || loadedStream.length || latestStream}
			<div
				data-testid="chat-message"
				data-streaming="true"
				class="relative self-start xl:mr-[20%] p-4 max-w-full rounded-xl bg-[#F2F4F7] data-dark:bg-[#5B7EE5] text-text group scroll-my-2"
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
		{/if}
	{:else if threadError}
		<div class="flex items-center justify-center sm:mx-24 my-0 h-full">
			<span class="relative -top-[0.05rem] text-3xl font-extralight">
				{threadError.error}
			</span>
			<div
				class="flex items-center ml-4 pl-4 min-h-10 border-l border-[#ccc] data-dark:border-[#666]"
			>
				<h1>{JSON.stringify(threadError.message)}</h1>
			</div>
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

			<div data-testid="stop-regen-btn" class="absolute -top-14 left-1/2 -translate-x-1/2">
				<!-- {#if generationStatus}
					<Button
						title="Stop generating"
						on:click={() => abortController?.abort()}
						class="flex gap-1 px-6 py-3 text-text bg-white data-dark:bg-[#202226] hover:bg-[#F0F0F0] data-dark:hover:bg-[#42464E] data-dark:border border-[#42464E] rounded-lg shadow-float"
					>
						<StopIcon class="h-6 w-6" />
						<span class="@xl:block hidden">Stop generating</span>
					</Button> -->
				{#if !generationStatus && thread?.length && thread.at(-1)?.role === 'assistant'}
					<Button
						variant="ghost"
						title="Regenerate previous response"
						on:click={handleRegenerate}
						class="flex gap-1.5 px-3.5 @xl:pr-4 py-2.5 text-text bg-white data-dark:bg-[#202226] hover:bg-[#F0F0F0] data-dark:hover:bg-[#42464E] data-dark:border border-[#42464E] rounded-lg shadow-float"
					>
						<RegenerateIcon class="h-6 w-6" />
						<span class="@xl:block hidden">Regenerate</span>
					</Button>
				{/if}
			</div>
		</div>
	</div>
</div>
