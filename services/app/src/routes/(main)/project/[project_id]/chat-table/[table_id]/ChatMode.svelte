<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { onMount, tick } from 'svelte';
	import { invalidate } from '$app/navigation';
	import { browser } from '$app/environment';
	import { page } from '$app/stores';
	import showdown from 'showdown';
	//@ts-expect-error - no types
	import showdownHtmlEscape from 'showdown-htmlescape';
	import '../../../../../../showdown-theme.css';
	import { codeblock, codehighlight, table } from '$lib/showdown';
	import type { ChatRequest, GenTableStreamEvent } from '$lib/types';

	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import { Button } from '$lib/components/ui/button';
	import SendIcon from '$lib/icons/SendIcon.svelte';
	import logger from '$lib/logger';

	const { PUBLIC_JAMAI_URL } = env;

	export let generationStatus: boolean;

	const converter = new showdown.Converter({
		tables: true,
		tasklists: true,
		disableForced4SpacesIndentedSublists: true,
		strikethrough: true,
		extensions: [showdownHtmlEscape, codeblock, codehighlight, table]
	});

	let thread: ChatRequest['messages'] = [];
	$: thread = $page.data.table.thread;

	let showRawTexts = false;

	let chatWindow: HTMLDivElement;
	let isLoading = false;

	//Chatbar
	let chatForm: HTMLFormElement;
	let chat: HTMLTextAreaElement;

	let chatMessage = '';
	let isResizing = false;
	let isResized = false;

	function resizeChat() {
		if (isResized) return; //? Prevents textarea from resizing by typing when chatbar is resized by user
		chat.style.height = '3rem';
		chat.style.height = (chat.scrollHeight >= 112 ? 112 : chat.scrollHeight) + 'px';
	}

	function interceptSubmit(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			chatForm.requestSubmit();
		}
	}

	async function handleChatSubmit(e: SubmitEvent) {
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
			},
			{
				role: 'assistant',
				content: ''
			}
		];

		//? Send message to the server
		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/chat/rows/add`, {
			method: 'POST',
			headers: {
				Accept: 'text/event-stream',
				'Content-Type': 'application/json'
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
			alert('Failed to add row: ' + (responseBody.message || JSON.stringify(responseBody)));
			chatMessage = cachedChatMessage;
		} else {
			generationStatus = true;

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
								thread = [
									...thread.slice(0, -1),
									{
										role: 'assistant',
										content:
											thread[thread.length - 1].content +
											(parsedValue.choices[0].message.content ?? '')
									}
								];
							} else {
								console.log('Unknown message:', parsedValue);
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

			generationStatus = false;

			invalidate('chat-table:slug');
		}
	}

	onMount(() => {
		chatWindow.scrollTop = chatWindow.scrollHeight;
	});

	const scrollToBotttom = async (a: any) => {
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
	$: scrollToBotttom(thread);

	function handleResize(e: MouseEvent) {
		if (!isResizing) return;

		const chatBottomSpace = 24;
		const chatbarMaxHeight = window.innerHeight * 0.65;
		const chatbarHeight = window.innerHeight - e.clientY - chatBottomSpace - 8;

		chat.style.height =
			(chatbarHeight >= chatbarMaxHeight ? chatbarMaxHeight : chatbarHeight) + 'px';

		isResized = true;
	}
</script>

<svelte:document on:mousemove={handleResize} on:mouseup={() => (isResizing = false)} />

<div
	bind:this={chatWindow}
	data-pw="chat-window"
	id="chat-window"
	class="relative grow flex flex-col xl:gap-4 gap-10 pr-4 pl-6 pt-6 pb-6 overflow-x-hidden overflow-y-auto [scrollbar-gutter:stable]"
>
	{#if !isLoading}
		{#each thread as threadItem, index}
			{@const { role, content: message } = threadItem}
			{#if role == 'assistant'}
				<div
					data-pw="chat-message"
					class="relative self-start xl:mr-[25%] p-4 max-w-full rounded-xl bg-[#F1F5FF] data-dark:bg-[#5B7EE5] text-text shadow-[0px_1px_3px_0px] shadow-black/[0.25] group scroll-my-2"
				>
					<p
						class="flex flex-col gap-4 response-message whitespace-pre-line text-sm {generationStatus &&
						index == thread.length - 1
							? '!block response-cursor'
							: ''}"
					>
						{#if showRawTexts || (generationStatus && index == thread.length - 1)}
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

					{#if !generationStatus && index == thread.length - 1}
						<!-- <div
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
						</div> -->
					{/if}
				</div>
			{:else if role == 'user'}
				<div
					data-pw="chat-message"
					class="relative self-end flex flex-col xl:ml-[25%] max-w-full rounded-xl bg-white data-dark:bg-[#444] shadow-[0px_1px_3px_0px] shadow-black/[0.25] group scroll-my-2"
				>
					<p class="p-4 text-sm [overflow-wrap:anywhere] focus:outline-none whitespace-pre-wrap">
						{message}
					</p>
				</div>
			{/if}
		{/each}
	{:else}
		<div class="absolute top-0 bottom-0 left-0 right-0 flex items-center justify-center">
			<LoadingSpinner class="h-6 w-6 text-[#4169e1] data-dark:text-[#5b7ee5]" />
		</div>
	{/if}
</div>

<div
	style="grid-template-rows: minmax(0, auto);"
	class="grid transition-[grid-template-rows] duration-300"
>
	<div
		style="grid-template-columns: auto;"
		class="@container grid items-end gap-2 px-6 pb-6 w-full transition-[background-color,grid-template-columns] duration-300"
	>
		<div
			class="relative flex items-center mt-2 p-1 w-full bg-white data-dark:bg-[#303338] text-text fill-secondary-content rounded-[0.75rem] shadow-[0px_1px_8px_0px] shadow-black/20 transition-colors"
		>
			<button
				tabindex="-1"
				on:mousedown={() => (isResizing = true)}
				class="absolute -top-[4px] left-0 right-0 mx-6 h-[10px] cursor-ns-resize focus:outline-none group"
			>
				<div
					class={`absolute top-[4px] h-[1px] w-full bg-black data-dark:bg-white rounded-md opacity-0 group-hover:opacity-100 ${
						isResizing && 'opacity-100'
					} transition-opacity`}
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
					class="p-3 pl-6 min-h-[48px] h-12 w-full bg-transparent resize-none outline-none placeholder:text-[#999999]"
				/>
			</form>

			<Button
				variant="ghost"
				title="Send message"
				on:click={() => {
					isResized = false;
					chatForm.requestSubmit();
				}}
				class={`h-12 rounded-full ${
					chatMessage ? 'fill-black data-dark:fill-white' : 'fill-[#999999] pointer-events-none'
				}`}
			>
				<SendIcon class="h-7" />
			</Button>

			<!-- <div data-pw="stop-regen-btn" class="absolute -top-14 left-1/2 -translate-x-1/2">
				{#if generationStatus}
					<Button
						title="Stop generating"
						on:click={() => abortController?.abort()}
						class="flex gap-1 px-6 py-3 text-text bg-white data-dark:bg-[#202226] hover:bg-[#F0F0F0] data-dark:hover:bg-[#42464E] data-dark:border border-[#42464E] rounded-lg shadow-float"
					>
						<StopIcon class="h-6 w-6" />
						<span class="@xl:block hidden">Stop generating</span>
					</Button>
				{:else if generationStatus.request == null && $activeLine.length}
					<Button
						title="Regenerate response"
						on:click={handleRegenerate}
						class="flex gap-1 px-6 py-3 text-text bg-white data-dark:bg-[#202226] hover:bg-[#F0F0F0] data-dark:hover:bg-[#42464E] data-dark:border border-[#42464E] rounded-lg shadow-float"
					>
						<RegenerateIcon class="h-6 w-6" />
						<span class="@xl:block hidden">Regenerate</span>
					</Button>
				{/if}
			</div> -->
		</div>
	</div>
</div>
