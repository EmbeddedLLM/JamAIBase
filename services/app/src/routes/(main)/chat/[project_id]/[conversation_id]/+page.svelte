<script lang="ts">
	import { env as publicEnv } from '$env/dynamic/public';
	import debounce from 'lodash/debounce';
	import { tick } from 'svelte';
	import {
		ArrowDownToLine,
		ArrowUp,
		AudioLines,
		Check,
		Copy,
		FileText,
		Trash2
	} from '@lucide/svelte';
	import { page } from '$app/state';
	import { afterNavigate, beforeNavigate, goto } from '$app/navigation';
	import logger from '$lib/logger';
	import showdown from 'showdown';
	//@ts-expect-error - no types
	import showdownHtmlEscape from 'showdown-htmlescape';
	import '../../../../../showdown-theme.css';
	import { codeblock, codehighlight, table as tableExtension } from '$lib/showdown';
	import { cn } from '$lib/utils';
	import { chatState } from '../../chat.svelte';
	import { chatCitationPattern, fileColumnFiletypes } from '$lib/constants';
	import type { ChatReferences, ChatThread } from '$lib/types';

	import { ChatControls, DeleteConvDialog, ReferencesSection } from './(components)';
	import { ChatFilePreview, ChatThumbsFetch } from '$lib/components/chat';
	import RowStreamIndicator from '$lib/components/preset/RowStreamIndicator.svelte';
	import UserDetailsBtn from '$lib/components/preset/UserDetailsBtn.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import RegenerateIcon from '$lib/icons/RegenerateIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import ChatAgentIcon from '$lib/icons/ChatAgentIcon.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';
	import TuneIcon from '$lib/icons/TuneIcon.svelte';

	const { PUBLIC_JAMAI_URL } = publicEnv;

	const converter = new showdown.Converter({
		tables: true,
		tasklists: true,
		disableForced4SpacesIndentedSublists: true,
		strikethrough: true,
		ghCompatibleHeaderId: true,
		extensions: [showdownHtmlEscape, codeblock, codehighlight, tableExtension]
	});

	let longestThreadCol = $derived(
		Object.keys(chatState.messages).reduce(
			(a, b) =>
				Array.isArray(chatState.messages[b].thread) &&
				(!a || chatState.messages[b].thread.length > chatState.messages[a].thread.length)
					? b
					: a,
			''
		)
	);

	let uris: { [rowID: string]: { [colID: string]: string } } = $derived({
		...Object.fromEntries(
			Object.entries(chatState.messages)
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
		),
		...{
			new: Object.fromEntries(
				Object.entries(chatState.uploadColumns).map(([col, val]) => [col, val.uri])
			)
		}
	});
	let rowThumbs: { [uri: string]: string } = $state({});
	let showFilePreview = $state<string | null>(null);

	let displayedLoadedStreams = $derived(
		Object.keys(chatState.messages).filter((colID) => {
			// Filter out columns to display
			const col = chatState.conversation?.cols?.find((col) => col.id === colID);
			return col?.gen_config?.object === 'gen_config.llm' && col.gen_config.multi_turn;
		})
	);

	let showRawTexts = $state(false);
	let showChatControls = $state<{ open: boolean; value: string | null }>({
		open: false,
		value: null
	});
	let showReferences = $state<{
		open: boolean;
		message: { columnID: string; rowID: string } | null;
		expandChunk: string | null;
		preview: NonNullable<ChatThread['thread'][number]['references']>['chunks'][number] | null;
	}>({
		open: false,
		message: null,
		expandChunk: null,
		preview: null
	});

	let isResizing = $state(false);
	let isResized = $state(false);
	let isEditingConvTitle = $state(false);
	let isDeletingConv = $state<string | null>(null);

	function resizeChat() {
		if (isResized || !chatState.chat) return; //? Prevents textarea from resizing by typing when chatbar is resized by user
		chatState.chat.style.height = '3rem';
		chatState.chat.style.height = Math.min(chatState.chat.scrollHeight, 180) + 'px';
	}

	function resizeEditContent(e?: Event & { currentTarget: EventTarget & HTMLTextAreaElement }) {
		const editFields = document.querySelectorAll('.edit-field');
		for (const editField of editFields) {
			(editField as HTMLElement).style.height = '';
			(editField as HTMLElement).style.height = editField.scrollHeight + 'px';
			if (e) {
				(editField as HTMLTextAreaElement).value = e.currentTarget.value;
			}
		}
	}

	function interceptSubmit(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			isResized = false;
			chatState.chatForm?.requestSubmit();
		}
	}

	function handleChatSubmit(e: SubmitEvent & { currentTarget: EventTarget & HTMLFormElement }) {
		e.preventDefault();
		if (chatState.loadingConversation || chatState.loadingMessages) return;

		chatState.sendMessage();
	}

	function handleResize(e: MouseEvent) {
		if (!chatState.chat) return;
		if (!isResizing) return;

		const chatTopSpace =
			(chatState.chatForm?.parentElement?.offsetHeight ?? 0) -
			(chatState.chatForm?.offsetHeight ?? 0);
		const chatBottomSpace = 24;
		const chatbarMaxHeight = window.innerHeight * 0.65;
		const chatbarHeight = window.innerHeight - e.clientY - chatTopSpace - chatBottomSpace;

		chatState.chat.style.height = Math.min(Math.max(chatbarHeight, 48), chatbarMaxHeight) + 'px';

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
				showChatControls = { open: false, value: null };
				showReferences = {
					open: true,
					message: {
						columnID,
						rowID
					},
					expandChunk: chunkID,
					preview: null
				};
			}
		}
	}

	let dragContainer = $state<HTMLElement | null>(null);
	let filesDragover = $state(false);
	function handleSelectFiles(files: File[], editing = false) {
		dragContainer
			?.querySelectorAll('input[type="file"]')
			?.forEach((el) => ((el as HTMLInputElement).value = ''));

		if (files.length === 0) return;
		if (
			Object.values(
				editing ? chatState.editingContent?.fileColumns ?? {} : chatState.uploadColumns
			).filter((val) => val.uri).length >= chatState.fileColumns.length
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
							chatState.fileColumns
								.filter(
									(c) =>
										!(
											editing
												? chatState.editingContent?.fileColumns ?? {}
												: chatState.uploadColumns
										)[c.id]?.uri?.trim()
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
						chatState.fileColumns
							.filter(
								(c) =>
									!(
										editing ? chatState.editingContent?.fileColumns ?? {} : chatState.uploadColumns
									)[c.id]?.uri?.trim()
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

		chatState.handleSaveFile(files, editing);
	}
	const handleDragLeave = () => (filesDragover = false);

	const debouncedScrollHandler = debounce(async (e: Event) => {
		const target = e.target as HTMLDivElement;
		const offset = target.scrollTop;
		const LOAD_THRESHOLD = 200;

		if (
			offset < LOAD_THRESHOLD &&
			!chatState.isLoadingMoreMessages &&
			!chatState.moreMessagesFinished
		) {
			await chatState.getMessages(false);
		}
	}, 300);

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

	function citationReplacer(
		match: string,
		word: string,
		columnID: string,
		rowID: string,
		references?: ChatReferences | null
	) {
		const citationIndices = match.match(/@(\d+)/g)?.map((m) => m.substring(1)) ?? [];
		return citationIndices
			.map(
				(idx) =>
					`<button 
						data-column="${columnID}" 
						data-row="${rowID}" 
						data-citation="${(references ?? chatState.messages[columnID]?.thread?.find((item) => item.row_id === rowID && item.references)?.references)?.chunks[Number(idx)]?.chunk_id}" 
						class="citation-btn aspect-square h-5 w-5 rounded-full bg-[#FFD8DF] text-xs text-[#475467]"
					>${Number(idx) + 1}</button>`
			)
			.join(' ');
	}

	beforeNavigate(() => {
		chatState.resetChat();
		showReferences = { ...showReferences, open: false, preview: null };
		rowThumbs = {};
	});

	afterNavigate(() => {
		chatState.getConversation();
		if (!chatState.generationStatus) {
			chatState.getMessages();
		} else {
			chatState.loadingMessages = false;
		}
	});
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

		if (e.key === 'Escape') {
			chatState.editingContent = null;
			isEditingConvTitle = false;
		}
	}}
/>

<svelte:head>
	<title>
		{chatState.conversation &&
			`${chatState.conversation.title || chatState.conversation.conversation_id} - `} JamAI Chat
	</title>
</svelte:head>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	bind:this={dragContainer}
	ondragover={(e) => {
		e.preventDefault();
		if (e.dataTransfer?.items) {
			if ([...e.dataTransfer.items].some((item) => item.kind === 'file')) {
				filesDragover = true;
			}
		}
	}}
	ondragleave={debounce(handleDragLeave, 50)}
	ondrop={(e) => {
		e.preventDefault();
		filesDragover = false;
		if (e.dataTransfer?.items) {
			handleSelectFiles(
				[...e.dataTransfer.items]
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
			handleSelectFiles([...(e.dataTransfer?.files ?? [])]);
		}
	}}
	class="relative grid {showReferences.open || showChatControls.open
		? showReferences.preview
			? 'grid-cols-[unset] grid-rows-[min-content_minmax(0,_auto)_60vh] md:grid-cols-[minmax(0,_auto)_48rem] md:grid-rows-[unset]'
			: 'grid-cols-[unset] grid-rows-[min-content_minmax(0,_auto)_60vh] md:grid-cols-[minmax(0,_auto)_24rem] md:grid-rows-[unset]'
		: 'grid-cols-[unset] grid-rows-[min-content_minmax(0,_auto)_0rem] md:grid-cols-[minmax(0,_auto)_0rem] md:grid-rows-[unset]'} h-1 grow bg-[#F2F4F7] transition-[grid-template-columns,grid-template-rows] duration-300 data-dark:bg-[#1E2024]"
>
	{#if chatState.conversation}
		<div
			class="-top-[3.25rem] left-36 flex w-[calc(100%-1rem)] items-center justify-between gap-2 pb-2 pl-0 md:absolute md:w-[calc(100%-9rem)]"
		>
			<div class="group/title flex items-center gap-1 text-sm sm:text-base">
				{@render chatHistoryIcon('flex-[0_0_auto] sm:h-5 sm:w-5 h-[18px] w-[18px]')}
				{#if !isEditingConvTitle}
					<span class="line-clamp-1">
						{chatState.conversation.title || '(no title)'}
					</span>
				{:else}
					<form
						id="editConvTitleForm"
						onsubmit={(e) => {
							e.preventDefault();
							if (!chatState.conversation) return;

							const formData = new FormData(e.currentTarget);
							const newTitle = formData.get('edited_title')?.toString();

							if (!newTitle) return;

							chatState.editConversationTitle(
								newTitle,
								page.params.conversation_id,
								page.params.project_id,
								() => {
									if (chatState.conversation) chatState.conversation.title = newTitle ?? '';
									isEditingConvTitle = false;

									chatState.refetchConversations();
								}
							);
						}}
					>
						<input
							type="text"
							name="edited_title"
							placeholder="Enter title"
							value={chatState.conversation.title}
							class="w-64 bg-transparent placeholder:italic"
						/>
					</form>
				{/if}

				<div
					class="flex items-center opacity-0 transition-opacity group-focus-within/title:opacity-100 group-hover/title:opacity-100"
				>
					{#if isEditingConvTitle}
						<Button
							variant="ghost"
							type="submit"
							form="editConvTitleForm"
							class="h-7 w-7 p-0 text-[#344054]"
						>
							<Check class="h-3.5 w-3.5" />
						</Button>

						<Button
							variant="ghost"
							onclick={() => (isEditingConvTitle = false)}
							class="h-7 w-7 p-0 text-[#344054]"
						>
							<CloseIcon class="h-3.5 w-3.5" />
						</Button>
					{:else}
						<Button
							variant="ghost"
							title="Edit title"
							onclick={() => (isEditingConvTitle = true)}
							class="h-7 w-7 p-0 text-[#344054]"
						>
							<EditIcon class="h-3.5 w-3.5" />
						</Button>

						<Button
							variant="ghost"
							title="Delete conversation"
							onclick={() => (isDeletingConv = page.params.conversation_id)}
							class="h-7 w-7 p-0 !text-[#F04438]"
						>
							<Trash2 class="h-3.5 w-3.5" />
						</Button>
					{/if}
				</div>
			</div>

			<div class="flex items-center gap-2">
				<div class="hidden items-center gap-2 sm:flex">
					<div
						class="hidden w-max max-w-36 items-center gap-1 rounded-xl border border-[#BF416E] bg-[#FFF7F8] px-1.5 py-1 text-xs text-[#BF416E] sm:text-sm lg:flex"
					>
						<ChatAgentIcon class="h-[18px] w-[18px] flex-[0_0_auto]" />
						<span class="line-clamp-1 w-max">
							{chatState.conversation?.parent_id}
						</span>
					</div>

					<Button
						variant="ghost"
						onclick={() => {
							showReferences = { ...showReferences, open: false, preview: null };
							showChatControls = { open: true, value: 'true' };
						}}
						class="h-8 w-8 p-0"
					>
						<TuneIcon class="h-5 w-5 text-[#1D2939]" />
					</Button>
				</div>

				<UserDetailsBtn class="mt-0" />
			</div>
		</div>
	{:else}
		<div class="block md:hidden"></div>
	{/if}

	<div class="flex min-h-0 flex-col @container/chat">
		<div
			bind:this={chatState.chatWindow}
			onscroll={debouncedScrollHandler}
			data-testid="chat-window"
			id="chat-window"
			class="relative flex grow flex-col gap-4 overflow-auto pt-6"
		>
			{#if chatState.conversation}
				{@const multiturnCols = Object.keys(chatState.messages)}
				{@const longestThreadColLen = chatState.messages[longestThreadCol]?.thread?.length ?? 0}
				{#each Array(longestThreadColLen).fill('') as _, index}
					<div
						class="group/message-container message-container flex flex-[0_0_auto] gap-3 px-3 transition-[padding] @2xl/chat:px-6 @4xl/chat:px-20 @6xl/chat:px-36 @7xl/chat:px-72 supports-[not(container-type:inline-size)]:px-6 supports-[not(container-type:inline-size)]:lg:px-20 supports-[not(container-type:inline-size)]:2xl:px-36 supports-[not(container-type:inline-size)]:3xl:px-72"
					>
						{#each Object.entries(chatState.messages) as [column, thread]}
							{@const threadItem = thread.thread[index]}
							{#if threadItem && threadItem.role !== 'system'}
								{#if threadItem.role === 'user'}
									{@const isEditingCell =
										chatState.editingContent?.rowID === threadItem.row_id &&
										chatState.editingContent.columnID === 'User'}
									<div
										data-role="user"
										class={cn(
											'ml-auto flex flex-col gap-1 transition-[padding]',
											multiturnCols.length > 1
												? 'min-w-full @5xl/chat:min-w-[50%] supports-[not(container-type:inline-size)]:xl:min-w-[50%]'
												: 'max-w-full',
											multiturnCols.length == 1
												? '@5xl/chat:pl-[20%] supports-[not(container-type:inline-size)]:xl:pl-[20%]'
												: 'last:pr-3 @2xl/chat:last:pr-6 @4xl/chat:last:pr-20 @5xl/chat:last:pr-0 supports-[not(container-type:inline-size)]:last:pr-6 supports-[not(container-type:inline-size)]:lg:last:pr-20 supports-[not(container-type:inline-size)]:xl:last:pr-0'
										)}
									>
										<div class="flex items-end justify-end">
											<div
												class:invisible={isEditingCell}
												class="flex items-center opacity-0 transition-opacity group-hover/message-container:opacity-100"
											>
												<Button
													variant="ghost"
													title="Edit content"
													onclick={async () => {
														chatState.editingContent = {
															rowID: threadItem.row_id,
															columnID: 'User',
															fileColumns:
																typeof threadItem.content !== 'string'
																	? Object.fromEntries(
																			threadItem.content
																				.filter((c) => c.type === 'input_s3')
																				.map((c) => [
																					c.column_name,
																					{ uri: c.uri, url: rowThumbs[c.uri] }
																				])
																		)
																	: {}
														};
														await tick();
														resizeEditContent();
													}}
													class="h-7 w-7 p-0 text-[#98A2B3]"
												>
													<EditIcon class="h-3.5 w-3.5" />
												</Button>
											</div>
										</div>

										<div
											data-testid="chat-message"
											class:w-full={multiturnCols.length > 1}
											class="group relative flex max-w-full scroll-my-2 flex-col gap-2 self-end rounded-xl bg-white p-4 data-dark:bg-[#444]"
										>
											{#if isEditingCell}
												{@render cellContentEditor(threadItem)}
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
											{@render cellContentEditorControls()}
										{/if}
									</div>
								{:else if threadItem.role === 'assistant'}
									{@const isEditingCell =
										chatState.editingContent?.rowID === threadItem.row_id &&
										chatState.editingContent?.columnID === column}
									<div
										data-role="assistant"
										class={cn(
											'group/message-container flex flex-col gap-1 transition-[padding]',
											multiturnCols.length > 1
												? 'min-w-full @5xl/chat:min-w-[50%] supports-[not(container-type:inline-size)]:xl:min-w-[50%]'
												: 'max-w-full',
											multiturnCols.length == 1
												? '@5xl/chat:pr-[20%] supports-[not(container-type:inline-size)]:xl:pr-[20%]'
												: 'last:pr-3 @2xl/chat:last:pr-6 @4xl/chat:last:pr-20 @5xl/chat:last:pr-0 supports-[not(container-type:inline-size)]:last:pr-6 supports-[not(container-type:inline-size)]:lg:last:pr-20 supports-[not(container-type:inline-size)]:xl:last:pr-0'
										)}
									>
										{#if !chatState.generationStatus?.includes(threadItem.row_id)}
											<div class="flex items-end justify-between px-4">
												<div class="flex items-center gap-2 text-sm">
													<span class="line-clamp-1 text-[#98A2B3]">
														{column}
													</span>
												</div>

												<div
													class:invisible={isEditingCell}
													class="flex items-center opacity-0 transition-opacity group-hover/message-container:opacity-100"
												>
													<Button
														variant="ghost"
														title="Edit content"
														onclick={async () => {
															chatState.editingContent = {
																rowID: threadItem.row_id,
																columnID: column,
																fileColumns:
																	typeof threadItem.content !== 'string'
																		? Object.fromEntries(
																				threadItem.content
																					.filter((c) => c.type === 'input_s3')
																					.map((c) => [
																						c.column_name,
																						{ uri: c.uri, url: rowThumbs[c.uri] }
																					])
																			)
																		: {}
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
															onclick={() => {
																showChatControls = { open: false, value: null };
																showReferences = {
																	open: true,
																	message: {
																		columnID: column,
																		rowID: threadItem.row_id
																	},
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

											<div
												data-testid="chat-message"
												class:w-full={multiturnCols.length > 1}
												class="group relative max-w-full scroll-my-2 self-start rounded-xl bg-[#F2F4F7] p-4 text-text data-dark:bg-[#5B7EE5]"
											>
												{#if isEditingCell}
													{@render cellContentEditor(threadItem)}
												{:else if typeof threadItem.content === 'string'}
													<p
														class="response-message flex flex-col gap-4 whitespace-pre-line text-sm"
													>
														{#if showRawTexts}
															{threadItem.content}
														{:else}
															{@const rawHtml = converter
																.makeHtml(threadItem.content)
																.replaceAll(chatCitationPattern, (match, word) =>
																	citationReplacer(
																		match,
																		word,
																		column,
																		threadItem.row_id,
																		threadItem.references
																	)
																)}
															{@html rawHtml}
														{/if}
													</p>
												{:else}
													{@const textContent = threadItem.content
														.filter((c) => c.type === 'text')
														.map((c) => c.text)
														.join('')}
													<!-- TODO: Insert images/file -->
													<p
														class="response-message flex flex-col gap-4 whitespace-pre-line text-sm"
													>
														{#if showRawTexts}
															{textContent}
														{:else}
															{@const rawHtml = converter
																.makeHtml(textContent)
																.replaceAll(chatCitationPattern, (match, word) =>
																	citationReplacer(
																		match,
																		word,
																		column,
																		threadItem.row_id,
																		threadItem.references
																	)
																)}
															{@html rawHtml}
														{/if}
													</p>
												{/if}
											</div>

											{#if isEditingCell}
												{@render cellContentEditorControls()}
											{/if}
										{:else}
											{@render generatingMessages(threadItem.row_id, column)}
										{/if}
									</div>
								{/if}
							{/if}
						{/each}
					</div>
				{/each}

				{#if chatState.generationStatus?.includes('new')}
					{@render generatingMessages('new')}
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

					{#if Object.keys(chatState.uploadColumns).length > 0}
						<div class="flex flex-wrap gap-2">
							{#each Object.entries(chatState.uploadColumns) as [uploadColumn, { uri }]}
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
										onclick={() => delete chatState.uploadColumns[uploadColumn]}
										class="absolute right-0 top-0 z-10 -translate-y-[30%] translate-x-[30%] rounded-full bg-black p-0.5 opacity-0 transition-[opacity,background-color] hover:bg-neutral-600 group-hover/image:opacity-100"
									>
										<CloseIcon class="h-4 w-4 text-white" />
									</button>
								</div>
							{/each}
						</div>
					{/if}

					<form
						bind:this={chatState.chatForm}
						onsubmit={handleChatSubmit}
						class="flex w-full gap-1"
					>
						<!-- svelte-ignore a11y_autofocus -->
						<textarea
							autofocus
							name="chatbar"
							placeholder="Enter message"
							bind:this={chatState.chat}
							bind:value={chatState.chatMessage}
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
								chatState.chatForm?.requestSubmit();
							}}
							disabled={(!chatState.chatMessage &&
								Object.values(chatState.uploadColumns).every((col) => !col.uri)) ||
								!!chatState.generationStatus}
							class="h-9 w-9 flex-[0_0_auto] rounded-full p-0"
						>
							<ArrowUp class="h-7" />
						</Button>
					</form>

					<div class="flex justify-between">
						{#if chatState.fileColumns.length > 0 && Object.keys(chatState.uploadColumns).length < chatState.fileColumns.length}
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
											chatState.fileColumns
												.filter((c) => !chatState.uploadColumns[c.id]?.uri?.trim())
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
	</div>

	{#if showChatControls.value}
		<ChatControls
			bind:showChatControls
			bind:showRawTexts
			bind:showFilePreview
			{rowThumbs}
			{getRawFile}
		/>
	{:else}
		<ReferencesSection bind:showReferences />
	{/if}
</div>

<DeleteConvDialog
	bind:isDeletingConv
	deleteCb={() => {
		goto(
			chatState.conversation
				? `/chat?${new URLSearchParams([
						['project_id', page.params.project_id],
						['agent', chatState.conversation.parent_id ?? '']
					])}`
				: '/chat'
		);

		chatState.refetchConversations();
	}}
/>
<ChatFilePreview bind:showFilePreview />
<ChatThumbsFetch {uris} bind:rowThumbs />

{#snippet cellContentEditor(threadItem: ChatThread['thread'][number])}
	{#if Object.keys(chatState.editingContent?.fileColumns ?? {}).length > 0}
		<div class="flex flex-wrap gap-2">
			{#each Object.entries(chatState.editingContent?.fileColumns ?? {}) as [uploadColumn, { uri, url }]}
				{#if uri}
					{@const fileType = fileColumnFiletypes.find(({ ext }) =>
						uri.toLowerCase().endsWith(ext)
					)?.type}
					<div class="group/image relative">
						<button
							title={uri.split('/').pop()}
							onclick={() => (showFilePreview = uri)}
							class:pointer-events-none={uri === 'loading'}
							class="flex h-32 w-32 items-center justify-center overflow-hidden rounded-xl bg-[#BF416E]"
						>
							{#if uri === 'loading'}
								<LoadingSpinner class="m-0 h-5 w-5 text-white" />
							{:else if url}
								{#if fileType === 'image'}
									<img src={url} alt="" class="z-0 h-full w-full object-cover" />
								{:else if fileType === 'audio'}
									<AudioLines class="h-8 w-8 text-white" />
								{:else if fileType === 'document'}
									<img src={url} alt="" class="z-0 h-full w-full object-cover" />
								{/if}
							{/if}
						</button>

						<button
							title="Delete file"
							onclick={() => {
								if (chatState.editingContent) {
									chatState.editingContent.fileColumns[uploadColumn] = { uri: '', url: '' };
								}
							}}
							class="absolute right-0 top-0 z-10 -translate-y-[30%] translate-x-[30%] rounded-full bg-black p-0.5 opacity-0 transition-[opacity,background-color] hover:bg-neutral-600 group-hover/image:opacity-100"
						>
							<CloseIcon class="h-4 w-4 text-white" />
						</button>
					</div>
				{/if}
			{/each}
		</div>
	{/if}

	<form
		id="editContentForm"
		onsubmit={(e) => {
			e.preventDefault();
			const formData = new FormData(e.currentTarget);
			const newContent = formData.get('edited_content');
			chatState.saveEditedContent({
				User: newContent?.toString()!,
				...Object.fromEntries(
					Object.entries(chatState.editingContent?.fileColumns ?? {}).map(([col, { uri }]) => [
						col,
						uri
					])
				)
			});
		}}
		class="flex"
	>
		<!-- svelte-ignore a11y_autofocus -->
		<textarea
			autofocus
			value={threadItem.role === 'user'
				? threadItem.user_prompt
				: typeof threadItem.content === 'string'
					? threadItem.content
					: threadItem.content.find((c) => c.type === 'text')?.text ?? ''}
			oninput={resizeEditContent}
			onkeydown={(e) => {
				if (e.key === 'Enter' && !e.shiftKey) {
					e.preventDefault();
					(e.currentTarget.parentElement as HTMLFormElement).requestSubmit();
				}
			}}
			name="edited_content"
			placeholder="Enter message"
			rows="1"
			cols="10000"
			class="edit-field h-min w-full resize-none bg-transparent text-sm [overflow-wrap:anywhere] focus:outline-none"
		></textarea>
	</form>

	{#if chatState.editingContent?.columnID === 'User'}
		{#if chatState.fileColumns.length > 0 && Object.values(chatState.editingContent?.fileColumns ?? {}).filter((val) => val.uri).length < chatState.fileColumns.length}
			<div class="flex justify-between">
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
								chatState.fileColumns
									.filter((c) => !chatState.editingContent?.fileColumns?.[c.id]?.uri?.trim())
									.map((c) => c.dtype)
									.includes(type)
							)
							.map(({ ext }) => ext)
							.join(',')}
						onchange={(e) => {
							e.preventDefault();
							handleSelectFiles([...(e.currentTarget.files ?? [])], true);
						}}
						multiple={false}
						class="fixed max-h-[0] max-w-0 overflow-hidden !border-none !p-0"
					/>
				</Button>

				<p></p>
			</div>
		{/if}
	{/if}
{/snippet}

{#snippet cellContentEditorControls()}
	<div class="flex justify-end gap-1">
		<Button
			variant="link"
			type="button"
			onclick={() => (chatState.editingContent = null)}
			class="px-4">Cancel</Button
		>
		<Button type="submit" form="editContentForm">Save</Button>
	</div>
{/snippet}

{#snippet generatingMessages(rowID: string, columnID?: string)}
	{#if columnID}
		{#each displayedLoadedStreams as key}
			{#if key === columnID}
				{@const loadedStream = chatState.loadedStreams[rowID][key]}
				{@const latestStream = chatState.latestStreams[rowID][key] ?? ''}
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
						{@html converter
							.makeHtml(loadedStream.join(''))
							.replaceAll(chatCitationPattern, (match, word) =>
								citationReplacer(
									match,
									word,
									columnID,
									rowID,
									chatState.loadedReferences?.[rowID]?.[columnID]
								)
							)}
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
				{@const loadedStream = chatState.loadedStreams[rowID][key]}
				{@const latestStream = chatState.latestStreams[rowID][key] ?? ''}
				<div
					class={cn(
						'group/message-container flex flex-col gap-1',
						displayedLoadedStreams.length > 1
							? 'min-w-full @5xl/chat:min-w-[50%] supports-[not(container-type:inline-size)]:xl:min-w-[50%]'
							: 'max-w-full',
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
							{@html converter
								.makeHtml(loadedStream.join(''))
								.replaceAll(chatCitationPattern, (match, word) =>
									citationReplacer(
										match,
										word,
										'new',
										rowID,
										chatState.loadedReferences?.[rowID]?.new
									)
								)}
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

{#snippet chatHistoryIcon(className = '')}
	<svg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" class={className}>
		<path
			d="M12.0778 8.14844C13.1182 8.14844 14.1159 8.56201 14.8516 9.29817C15.5872 10.0343 16.0006 11.0328 16.0006 12.0739C16.0031 12.8466 15.7748 13.6024 15.3452 14.2444L16.0006 15.9993L13.7946 15.6021C13.264 15.861 12.682 15.9968 12.0917 15.9993C11.5015 16.0018 10.9183 15.8709 10.3856 15.6165C9.85288 15.3622 9.38442 14.9907 9.0151 14.53C8.64579 14.0693 8.38513 13.5311 8.25256 12.9555C8.12 12.3799 8.11893 11.7819 8.24945 11.2058C8.37998 10.6298 8.63872 10.0907 9.00639 9.62865C9.37406 9.16659 9.8412 8.79353 10.373 8.53724C10.9048 8.28095 11.4875 8.14805 12.0778 8.14844Z"
			stroke="#1D2939"
			stroke-width="1.3"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M12.6394 5.84932C12.0178 5.05783 11.1651 4.47999 10.1999 4.19624C9.23473 3.9125 8.20514 3.93697 7.25451 4.26626C6.30388 4.59554 5.47952 5.21325 4.89618 6.03338C4.31285 6.85349 3.9996 7.83523 4.00002 8.84187C3.99716 9.79875 4.28 10.7347 4.81227 11.5296L4.00002 13.6909L5.95681 13.3399"
			stroke="#1D2939"
			stroke-width="1.3"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
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
