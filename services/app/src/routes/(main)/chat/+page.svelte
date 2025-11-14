<script lang="ts">
	import { env as publicEnv } from '$env/dynamic/public';
	import debounce from 'lodash/debounce';
	import Fuse from 'fuse.js';
	import { ArrowDownToLine, ArrowLeft, ArrowUp, AudioLines } from '@lucide/svelte';
	import { beforeNavigate, goto, invalidate } from '$app/navigation';
	import { page } from '$app/state';
	import { activeOrganization } from '$globalStore';
	import { chatState } from './chat.svelte';
	import logger from '$lib/logger';
	import { fileColumnFiletypes } from '$lib/constants';
	import type { GenTable, Project } from '$lib/types';

	import ProjectAgents from './(components)/ProjectAgents.svelte';
	import SearchBar from '$lib/components/preset/SearchBar.svelte';
	import { ChatFilePreview, ChatThumbsFetch } from '$lib/components/chat';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import ChatAgentIcon from '$lib/icons/ChatAgentIcon.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import CloseIcon from '$lib/icons/CloseIcon.svelte';

	const { PUBLIC_JAMAI_URL } = publicEnv;

	let { data } = $props();

	let selectingFilterOrg = $state(true);
	let loadingAgents = $state(true);
	let searchQuery = $state('');

	let chat: HTMLTextAreaElement | null = $state(null);
	let chatForm: HTMLFormElement | null = $state(null);
	let isResizing = $state(false);
	let isResized = $state(false);

	let loadingAgent = $state<boolean | any>(false);

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

	let loadingChatSubmit = $state(false);

	function resizeChat() {
		if (isResized || !chat) return; //? Prevents textarea from resizing by typing when chatbar is resized by user
		chat.style.height = '9rem';
		chat.style.height = (chat.scrollHeight >= 460 ? 460 : chat.scrollHeight) + 'px';
	}

	function interceptSubmit(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			isResized = false;
			chatForm?.requestSubmit();
		}
	}

	async function handleChatSubmit(
		e: SubmitEvent & { currentTarget: EventTarget & HTMLFormElement }
	) {
		e.preventDefault();
		if (!chatState.agent || loadingAgent) return;

		loadingChatSubmit = true;
		await chatState.sendMessage();
		loadingChatSubmit = false;
	}

	let dragContainer = $state<HTMLElement | null>(null);
	let filesDragover = $state(false);
	function handleSelectFiles(files: File[]) {
		dragContainer
			?.querySelectorAll('input[type="file"]')
			?.forEach((el) => ((el as HTMLInputElement).value = ''));

		if (files.length === 0) return;
		if (Object.keys(chatState.uploadColumns).length >= chatState.fileColumns.length) {
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
								.filter((c) => !chatState.uploadColumns[c.id]?.uri?.trim())
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
							.filter((c) => !chatState.uploadColumns[c.id]?.uri?.trim())
							.map((c) => c.dtype)
							.includes(type)
					)
					.map(({ ext }) => ext)
					.join(', ')
					.replaceAll('.', '')}`
			);
			return;
		}

		chatState.handleSaveFile(files);
	}
	const handleDragLeave = () => (filesDragover = false);

	async function getAgent() {
		const projectId = page.url.searchParams.get('project_id');
		const agentId = page.url.searchParams.get('agent');
		if (!projectId || !agentId) return;

		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/conversations/agents?${new URLSearchParams([
				['agent_id', agentId]
			])}`,
			{
				headers: {
					'x-project-id': projectId
				}
			}
		);
		const responseBody = await response.json();

		if (response.ok) {
			chatState.agent = responseBody;
			loadingAgent = false;
		} else {
			loadingAgent = responseBody;
			logger.error('CHAT_GET_AGENT', responseBody);
			toast.error('Failed to get agent details', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}
	}

	$effect(() => {
		page.url.searchParams.get('agent');
		getAgent();
	});

	async function getAgents(offset = 0) {
		if (!$activeOrganization) return;
		const limit = 100;

		const searchParams = new URLSearchParams([
			['offset', offset.toString()],
			['limit', limit.toString()],
			['order_by', 'name'],
			['organization_id', $activeOrganization.id],
			['list_chat_agents', 'true']
		]);

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/projects/list?${searchParams}`, {
			credentials: 'same-origin'
		});
		const responseBody = await response.json();

		if (response.ok) {
			chatState.agents = {
				...chatState.agents,
				...Object.fromEntries(
					responseBody.items.map((project: Project & { chat_agents: GenTable[] }) => [
						project.id,
						project.chat_agents
					])
				)
			};
			return responseBody;
		} else {
			logger.error('CHAT_LIST_AGENTS', responseBody);
			console.error(responseBody);
			toast.error(`Failed to fetch agents`, {
				id: responseBody?.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody?.message || JSON.stringify(responseBody),
					requestID: responseBody?.request_id
				}
			});
			throw responseBody;
		}
	}

	function fetchAgents(offset = 0) {
		getAgents(offset).then((body) => {
			if (body.total > Object.keys(chatState.agents).length) {
				fetchAgents(Object.keys(chatState.agents).length);
			} else {
				loadingAgents = false;
			}
		});
	}

	async function fetchAgentsNew() {
		loadingAgents = true;
		chatState.agents = {};
		fetchAgents(0);
	}

	$effect(() => {
		if ($activeOrganization) fetchAgentsNew();
	});

	const filterAgents = (project: Project) => {
		const fuse = new Fuse(chatState.agents[project.id] ?? [], {
			keys: ['id', 'title'],
			threshold: 0.4,
			includeScore: false
		});
		return searchQuery.trim()
			? fuse.search(searchQuery).map((result) => result.item)
			: chatState.agents[project.id] ?? [];
	};

	beforeNavigate(() => {
		chatState.uploadColumns = {};
	});
</script>

<svelte:head>
	<title>JamAI Chat</title>
</svelte:head>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<section
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
	class="relative flex h-1 grow flex-col items-center justify-center gap-5 px-6 py-10 {page.url.searchParams.has(
		'agent'
	)
		? 'overflow-auto'
		: 'overflow-hidden sm:overflow-auto'}"
>
	<div
		class="flex select-none items-center gap-4 {page.url.searchParams.has('agent')
			? 'w-[clamp(0px,50rem,100%)]'
			: 'w-[clamp(0px,60rem,100%)]'}"
	>
		<svg
			width="18"
			height="18"
			viewBox="0 0 18 18"
			fill="none"
			xmlns="http://www.w3.org/2000/svg"
			class="flex-[0_0_auto]"
		>
			<path
				d="M10.4532 0C14.6212 0 18 4.02944 18 9V18L7.54682 18C3.37883 18 0 13.9706 0 9L0 0L10.4532 0Z"
				fill="url(#paint0_linear_6514_86948)"
			/>
			<circle cx="9" cy="9" r="3" fill="#F2F4F7" />
			<defs>
				<linearGradient
					id="paint0_linear_6514_86948"
					x1="18"
					y1="-0.230769"
					x2="5.86733e-08"
					y2="18"
					gradientUnits="userSpaceOnUse"
				>
					<stop stop-color="#1A2C70" />
					<stop offset="1" stop-color="#AF405D" />
				</linearGradient>
			</defs>
		</svg>

		<h1
			style="background: linear-gradient(134.64deg, #1A2C70 -0.65%, #AF405D 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;"
			class="text-3xl font-medium"
		>
			Hello, {data.user?.name}
		</h1>

		{#if page.url.searchParams.has('agent')}
			<div class="ml-auto flex items-center gap-2 self-end px-1">
				<div
					class="flex items-center gap-1 rounded-xl border border-[#BF416E] bg-[#FFF7F8] px-1.5 py-1 text-sm text-[#BF416E]"
				>
					<ChatAgentIcon class="h-[18px] w-[18px] flex-[0_0_auto]" />
					<span class="line-clamp-2">
						{page.url.searchParams.get('agent')}
					</span>
				</div>

				<button
					onclick={() => {
						page.url.searchParams.delete('agent');
						page.url.searchParams.delete('project_id');
						goto(`?${page.url.searchParams}`, { replaceState: true });
					}}
					class="text-[#BF416E]"
				>
					<EditIcon class="h-3.5 w-3.5" />
				</button>
			</div>
		{/if}
	</div>

	{#if !page.url.searchParams.has('agent')}
		<div
			class="grid h-[clamp(0px,35rem,100%)] w-[200%] grid-cols-2 rounded-xl bg-white shadow-float sm:w-[clamp(0px,60rem,100%)] sm:translate-x-[unset] sm:grid-cols-[12rem_minmax(0,_auto)] {selectingFilterOrg
				? 'translate-x-[25%]'
				: '-translate-x-[25%]'} transition-transform"
		>
			<div style="box-shadow: 2px 0px 4px 0px rgba(0, 0, 0, 0.06);" class="flex flex-col gap-2">
				<span class="mx-4 mt-4 text-sm font-medium uppercase text-[#98A2B3]">Organizations</span>

				<ul class="flex h-1 grow flex-col gap-1 overflow-auto px-2 pb-2">
					{#each data.user?.organizations ?? [] as organization (organization.id)}
						<button
							onclick={async () => {
								if (organization.id !== $activeOrganization?.id) {
									activeOrganization.setOrgCookie(organization.id);
									invalidate('layout:root');
								}
								selectingFilterOrg = false;
							}}
							class="break-words rounded-lg px-2 py-1.5 text-left text-[15px] transition-colors {$activeOrganization?.id ===
							organization.id
								? 'bg-[#FFEFF2] text-[#950048]'
								: 'hover:bg-[#F2F4F7] data-dark:hover:bg-white/[0.04]'}"
						>
							{organization.name}
						</button>
					{/each}
				</ul>
			</div>

			<div class="flex flex-col gap-2">
				{#if $activeOrganization}
					<div class="relative flex items-center justify-center px-10">
						<Button
							variant="ghost"
							onclick={() => (selectingFilterOrg = true)}
							class="absolute left-4 flex aspect-square h-[unset] p-1.5 sm:hidden"
						>
							<ArrowLeft size={20} class="text-[#344054]" />
						</Button>

						<p class="mt-4 px-4 text-center text-[#1D2939]">Choose agent to start conversation</p>
					</div>

					<div class="relative flex items-center justify-center px-10">
						<SearchBar
							bind:searchQuery
							isLoadingSearch={loadingAgents}
							debouncedSearch={async () => {}}
							label="Search agents"
							placeholder="Search agents"
							class="place-self-end {searchQuery
								? 'sm:w-[14rem]'
								: 'w-[12rem] sm:w-[14rem]'} [&_*]:!cursor-text"
						/>
					</div>

					<div class="flex h-1 grow flex-col overflow-auto">
						{#each (data.user?.projects ?? []).filter((p) => p.organization_id === $activeOrganization.id) as project (project.id)}
							{@const filteredAgents = filterAgents(project)}
							{#if !searchQuery || filteredAgents?.length > 0}
								<ProjectAgents {project} agents={filteredAgents} {loadingAgents} />
							{/if}
						{/each}
					</div>
				{/if}
			</div>
		</div>
	{:else}
		<div
			style="box-shadow: 0px 4px 12px 0px rgba(0, 0, 0, 0.06);"
			class="flex w-[clamp(0px,50rem,100%)] flex-col gap-2 rounded-xl bg-white p-3"
		>
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
										<AudioLines class="h-8 w-8 text-white" />
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

			<form bind:this={chatForm} onsubmit={handleChatSubmit} class="flex gap-1">
				<textarea
					bind:this={chat}
					bind:value={chatState.chatMessage}
					disabled={loadingChatSubmit}
					name="chat-prompt"
					id="chat-prompt"
					placeholder="Enter message"
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
					class="h-36 min-h-[48px] w-full resize-none bg-transparent outline-none placeholder:text-[#999999]"
				></textarea>

				<Button
					type="submit"
					disabled={(!chatState.chatMessage &&
						Object.values(chatState.uploadColumns).every((col) => !col.uri)) ||
						loadingChatSubmit}
					class="aspect-square h-8 w-8 flex-[0_0_auto] p-0"
				>
					{#if !loadingChatSubmit}
						<ArrowUp class="h-5 w-5" />
					{:else}
						<LoadingSpinner class="ml-0 mr-0 h-5 w-5" />
					{/if}
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
	{/if}
</section>

<ChatFilePreview bind:showFilePreview />
<ChatThumbsFetch {uris} bind:rowThumbs />
