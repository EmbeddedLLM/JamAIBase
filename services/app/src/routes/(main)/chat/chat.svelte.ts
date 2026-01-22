import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import { page } from '$app/state';
import { env as publicEnv } from '$env/dynamic/public';
import logger from '$lib/logger';
import type {
	ChatReferences,
	ChatThread,
	ChatThreads,
	Conversation,
	GenTable,
	GenTableStreamEvent,
	ReferenceChunk
} from '$lib/types';
import { waitForElement } from '$lib/utils';
import { tick } from 'svelte';
import { v4 as uuidv4 } from 'uuid';

import { CustomToastDesc, toast } from '$lib/components/ui/sonner';
import { fileColumnFiletypes } from '$lib/constants';
import axios from 'axios';

const { PUBLIC_JAMAI_URL } = publicEnv;

export class ChatState {
	// Agents
	agents: Record<string, GenTable[]> = $state({});

	// Conversations
	fetchController: AbortController | null = null;
	conversations: Conversation[] = $state([]);
	loadingConvsError: { status: number; message: string } | null = $state(null);
	isLoadingConvs = $state(true);
	isLoadingMoreConvs = $state(false);
	moreConvsFinished = false;
	currentOffsetConvs = 0;
	private limitConvs = 50;
	searchQuery = $state('');
	isLoadingSearch = $state(false);

	// Actual chat
	agent = $state<
		(Omit<Conversation, 'conversation_id' | 'parent_id'> & { agent_id: string }) | null
	>(null);
	conversation: Conversation | null = $state(null);
	loadingConversation: any = $state(true);
	messages: ChatThreads['threads'] = $state({});
	loadingMessages: any = $state(true);
	chatWindow: HTMLDivElement | null = $state(null);
	chatForm: HTMLFormElement | null = $state(null);
	chat: HTMLTextAreaElement | null = $state(null);
	chatMessage = $state('');
	editingContent: {
		rowID: string;
		columnID: string;
		fileColumns: Record<string, { uri: string; url: string }>;
	} | null = $state(null);
	generationStatus: string[] | null = $state(null);
	isLoadingMoreMessages = $state(false);
	moreMessagesFinished = false;
	currentOffsetMessages = 0;
	private limitMessages = 10;
	fileColumns = $derived(
		(!page.params.conversation_id ? this.agent : this.conversation)?.cols.filter(
			(col) => col.dtype === 'image' || col.dtype === 'audio' || col.dtype === 'document'
		) ?? []
	);
	uploadColumns: Record<string, { uri: string; url: string }> = $state({});
	loadedStreams: Record<string, Record<string, string[]>> = $state({});
	latestStreams: Record<string, Record<string, string>> = $state({});
	reasoningContentStreams: Record<string, Record<string, string>> = $state({});
	loadedReferences: Record<string, Record<string, ChatReferences>> | null = null;

	/** Output details dialog */
	showOutputDetails: {
		open: boolean;
		activeCell: { rowID: string; columnID: string } | null;
		activeTab: string;
		message: {
			content: string;
			error: { message?: string } | string | null;
			chunks: ReferenceChunk[];
			fileUrl?: string;
		} | null;
		reasoningContent: string | null;
		reasoningTime: number | null;
		expandChunk: string | null;
		preview: ReferenceChunk | null;
	} = $state({
		open: false,
		activeCell: null,
		activeTab: 'answer',
		message: null,
		reasoningContent: null,
		reasoningTime: null,
		expandChunk: null,
		preview: null
	});

	private getConvController: AbortController | null = null;
	private getMessagesController: AbortController | null = null;

	//TODO: Optimize this, load inline without creating thread object
	// (if new message is generating, load another row of messages, show content from loaded streams)
	getNewMessageAsThreads(): typeof this.messages {
		const longestThreadCol = Object.keys(this.messages).reduce(
			(a, b) =>
				Array.isArray(this.messages[b].thread) &&
				(!a || this.messages[b].thread.length > this.messages[a].thread.length)
					? b
					: a,
			''
		);
		const longestThreadColLen = this.messages[longestThreadCol]?.thread?.length ?? 0;
		return this.generationStatus?.includes('new')
			? Object.fromEntries(
					this.conversation!.cols.map((col) =>
						col.gen_config?.object === 'gen_config.llm' && col.gen_config.multi_turn
							? [
									[
										col.id,
										{
											object: 'chat.thread',
											thread: [
												...new Array(longestThreadColLen).fill(null),
												{
													reasoning_content: this.reasoningContentStreams.new?.[col.id] ?? null,
													reasoning_time: null,
													row_id: 'new',
													role: 'assistant',
													content:
														(this.loadedStreams.new?.[col.id]?.join('') ?? '') +
														(this.latestStreams.new?.[col.id] ?? ''),
													name: null,
													user_prompt: null,
													references: null
												}
											]
										} as ChatThread
									]
								]
							: []
					).flat()
				)
			: {};
	}

	async getConversation() {
		if (!page.params.project_id || !page.params.conversation_id) return;

		this.getConvController?.abort('Duplicate');
		this.getConvController = new AbortController();

		try {
			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/conversations?${new URLSearchParams([
					['conversation_id', page.params.conversation_id]
				])}`,
				{
					headers: {
						'x-project-id': page.params.project_id
					},
					signal: this.getConvController.signal
				}
			);
			const responseBody = await response.json();

			if (response.ok) {
				this.conversation = responseBody;
				this.loadingConversation = false;
			} else {
				this.loadingConversation = responseBody;
				logger.error('CHAT_GET_CONV', responseBody);
				toast.error('Failed to load conversation', {
					id: responseBody.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody.message || JSON.stringify(responseBody),
						requestID: responseBody.request_id
					}
				});
			}
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Duplicate') {
				console.error(err);
			}
		}
	}

	async getMessages(scroll = true) {
		if (!page.params.project_id || !page.params.conversation_id) return;

		this.getMessagesController?.abort('Duplicate');
		this.getMessagesController = new AbortController();

		try {
			const searchParams = new URLSearchParams([
				['conversation_id', page.params.conversation_id],
				['offset', this.currentOffsetMessages.toString()],
				['limit', this.limitMessages.toString()],
				['order_ascending', 'false']
				// ['organization_id', $activeOrganization.id]
			]);

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/conversations/threads?${searchParams}`,
				{
					headers: {
						'x-project-id': page.params.project_id
					},
					signal: this.getMessagesController.signal
				}
			);
			const responseBody = await response.json();

			this.currentOffsetMessages += this.limitMessages;

			if (response.ok) {
				this.messages = responseBody.threads;

				this.moreMessagesFinished = true;

				//! Old paginated response
				/* if (responseBody.items.length) {
					if (this.chatWindow && !scroll) {
						this.chatWindow.scrollTop += 1;
					}
					this.messages = [...responseBody.items.reverse(), ...this.messages];
				} else {
					this.moreMessagesFinished = true;
				} */
				this.loadingMessages = false;
			} else {
				this.loadingMessages = responseBody;
				logger.error('CHAT_GET_MESSAGES', responseBody);
				toast.error('Failed to load messages', {
					id: responseBody.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody.message || JSON.stringify(responseBody),
						requestID: responseBody.request_id
					}
				});
			}

			if (scroll) {
				await tick();
				if (this.messages.length) {
					await waitForElement('[data-testid=chat-message]');
				}
				await this.scrollChatToBottom();
			}
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Duplicate') {
				console.error(err);
			}
		}
	}

	async sendMessage() {
		if (
			this.generationStatus ||
			(!this.chatMessage.trim() && Object.values(chatState.uploadColumns).every((col) => !col.uri))
		)
			return;

		const cachedPrompt = this.chatMessage;
		const cachedFiles = structuredClone($state.snapshot(this.uploadColumns));
		this.chatMessage = '';
		this.uploadColumns = {};

		if (this.chat) this.chat.style.height = '3rem';

		//? Get agent threads
		if (!page.params.conversation_id) {
			if (!this.agent) return;
			const agentThreadRes = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/conversations/threads?${new URLSearchParams([
					['conversation_id', this.agent.agent_id]
				])}`,
				{
					headers: {
						'x-project-id': page.params.project_id ?? page.url.searchParams.get('project_id') ?? ''
					}
				}
			);
			const agentThreadBody = await agentThreadRes.json();

			if (agentThreadRes.ok) {
				this.messages = Object.fromEntries(
					Object.entries((agentThreadBody as ChatThreads).threads).map(([outCol, thread]) => [
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
			} else {
				logger.error('CHAT_CONV_GETAGENT', agentThreadBody);
				toast.error('Failed to send message', {
					id: agentThreadBody.message || JSON.stringify(agentThreadBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: agentThreadBody.message || JSON.stringify(agentThreadBody),
						requestID: agentThreadBody.request_id
					}
				});
				return;
			}
		} else {
			//? Add user message to the chat
			this.messages = Object.fromEntries(
				Object.entries(this.messages).map(([outCol, thread]) => [
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
		}

		this.generationStatus = ['new'];
		this.loadedStreams = {
			new: Object.fromEntries(
				(page.params.conversation_id ? this.conversation! : this.agent!).cols
					.map((col) =>
						col.gen_config?.object === 'gen_config.llm' && col.gen_config.multi_turn
							? [[col.id, []]]
							: []
					)
					.flat()
			)
		};
		this.latestStreams = {
			new: Object.fromEntries(
				(page.params.conversation_id ? this.conversation! : this.agent!).cols
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
		if (this.chatWindow) this.chatWindow.scrollTop = this.chatWindow.scrollHeight;

		//? Send message to the server
		const apiUrl = page.params.conversation_id
			? '/api/owl/conversations/messages'
			: '/api/owl/conversations';
		const response = await fetch(`${PUBLIC_JAMAI_URL}${apiUrl}`, {
			method: 'POST',
			headers: {
				Accept: 'text/event-stream',
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id ?? page.url.searchParams.get('project_id') ?? ''
			},
			body: JSON.stringify({
				data: {
					User: cachedPrompt,
					...Object.fromEntries(
						Object.entries(cachedFiles).map(([uploadColumn, val]) => [uploadColumn, val.uri])
					)
				},
				agent_id: page.params.conversation_id ? undefined : this.agent?.agent_id,
				conversation_id: page.params.conversation_id || undefined
			})
		});

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error(this.conversation ? 'CHAT_MESSAGE_ADD' : 'CHAT_CONV_CREATE', responseBody);
			toast.error('Failed to add message', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
			this.messages = Object.fromEntries(
				Object.entries(this.messages).map(([outCol, thread]) => [
					outCol,
					{
						...thread,
						thread: thread.thread.slice(0, -1)
					}
				])
			);
			this.chatMessage = cachedPrompt;
			this.uploadColumns = cachedFiles;
		} else {
			const { row_id } = await this.parseStream(
				response.body!.pipeThrough(new TextDecoderStream()).getReader(),
				true
			);

			this.loadedStreams = Object.fromEntries(
				Object.entries(this.loadedStreams).map(([row, colStreams]) => [
					row,
					Object.fromEntries(
						Object.entries(colStreams).map(([col, streams]) => [
							col,
							[...streams, this.latestStreams[row][col]]
						])
					)
				])
			);

			this.messages = Object.fromEntries(
				Object.entries(this.messages).map(([outCol, thread]) => {
					const loadedStreamCol = this.loadedStreams.new[outCol];
					const colReferences = this.loadedReferences?.new?.[outCol] ?? null;
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

			this.getMessages();
			if (apiUrl === '/api/owl/conversations') {
				chatState.refetchConversations();
			}
		}

		this.generationStatus = null;
		this.loadedStreams = {};
		this.latestStreams = {};
		this.loadedReferences = {};
	}

	async handleSaveFile(files: File[], editing = false) {
		const formData = new FormData();
		formData.append('file', files[0]);

		const nextAvailableCol = this.fileColumns.find(
			(col) =>
				!(editing ? (this.editingContent?.fileColumns ?? {}) : this.uploadColumns)[col.id]?.uri &&
				fileColumnFiletypes
					.filter(({ type }) => col.dtype === type)
					.map(({ ext }) => ext)
					.includes('.' + (files[0].name.split('.').pop() ?? '').toLowerCase())
		);
		if (!nextAvailableCol)
			return alert('No more files of this type can be uploaded: all columns filled.');

		if (editing) {
			if (this.editingContent) {
				this.editingContent.fileColumns[nextAvailableCol.id] = {
					uri: 'loading',
					url: ''
				};
			}
		} else {
			this.uploadColumns[nextAvailableCol.id] = {
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
						if (this.editingContent) {
							this.editingContent.fileColumns[nextAvailableCol.id] = {
								uri: uploadRes.data.uri,
								url: urlBody.urls[0]
							};
						}
					} else {
						this.uploadColumns[nextAvailableCol.id] = {
							uri: uploadRes.data.uri,
							url: urlBody.urls[0]
						};
					}
				} else {
					if (editing) {
						if (this.editingContent) {
							this.editingContent.fileColumns[nextAvailableCol.id] = {
								uri: uploadRes.data.uri,
								url: ''
							};
						}
					} else {
						this.uploadColumns[nextAvailableCol.id] = { uri: uploadRes.data.uri, url: '' };
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

	async regenMessage(rowID: string) {
		if (this.generationStatus) return;

		const cachedMessages = $state.snapshot(this.messages);

		this.messages = Object.fromEntries(
			Object.entries(this.messages).map(([outCol, thread]) => {
				return [
					outCol,
					{
						...thread,
						thread: thread.thread.map((v) =>
							v.row_id === rowID && v.role === 'assistant'
								? { ...v, row_id: rowID, content: '', references: null }
								: v
						)
					}
				];
			})
		);

		const longestThreadCol = Object.keys(chatState.messages).reduce(
			(a, b) =>
				Array.isArray(chatState.messages[b].thread) &&
				(!a || chatState.messages[b].thread.length > chatState.messages[a].thread.length)
					? b
					: a,
			''
		);
		const rowsToRegen = this.messages[longestThreadCol].thread
			.filter((m) => m.role !== 'User')
			.slice(this.messages[longestThreadCol].thread.findIndex((m) => m.row_id === rowID))
			.map((m) => m.row_id);
		this.loadedStreams = Object.fromEntries(
			rowsToRegen.map((row) => [
				row,
				Object.fromEntries(
					this.conversation!.cols.map((col) =>
						col.gen_config?.object === 'gen_config.llm' && col.gen_config.multi_turn
							? [[col.id, []]]
							: []
					).flat()
				)
			])
		);
		this.latestStreams = Object.fromEntries(
			rowsToRegen.map((row) => [
				row,
				Object.fromEntries(
					this.conversation!.cols.map((col) =>
						col.gen_config?.object === 'gen_config.llm' && col.gen_config.multi_turn
							? [[col.id, '']]
							: []
					).flat()
				)
			])
		);

		if (
			this.showOutputDetails.activeCell?.rowID &&
			rowsToRegen.includes(this.showOutputDetails.activeCell.rowID)
		) {
			this.closeOutputDetails();
		}

		this.generationStatus = rowsToRegen;

		//? Show user message
		await tick();

		//? Send message to the server
		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/conversations/messages/regen`, {
			method: 'POST',
			headers: {
				Accept: 'text/event-stream',
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id ?? ''
			},
			body: JSON.stringify({
				conversation_id: page.params.conversation_id,
				row_id: rowID
			})
		});

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error('CHAT_MESSAGE_REGEN', responseBody);
			toast.error('Failed to regen message response', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
			this.messages = cachedMessages;
		} else {
			await this.parseStream(response.body!.pipeThrough(new TextDecoderStream()).getReader());

			this.loadedStreams = Object.fromEntries(
				Object.entries(this.loadedStreams).map(([row, colStreams]) => [
					row,
					Object.fromEntries(
						Object.entries(colStreams).map(([col, streams]) => [
							col,
							[...streams, this.latestStreams[row][col]]
						])
					)
				])
			);

			this.messages = Object.fromEntries(
				Object.entries(this.messages).map(([outCol, thread]) => {
					return [
						outCol,
						{
							...thread,
							thread: [
								...thread.thread.map((v) =>
									rowsToRegen.includes(v.row_id) && v.role === 'assistant'
										? {
												...v,
												content: this.loadedStreams[v.row_id]?.[outCol]?.join('') ?? v.content,
												references: this.loadedReferences?.[v.row_id]?.[outCol] ?? v.references
											}
										: v
								)
							]
						}
					];
				})
			);

			this.getMessages();
		}

		this.generationStatus = null;
		this.loadedStreams = {};
		this.latestStreams = {};
		this.loadedReferences = {};
	}

	async saveEditedContent(newContent: Record<string, string>) {
		if (!this.editingContent || this.generationStatus) return;

		this.closeOutputDetails();

		// const editingMessage = this.messages.find((m) => m.ID === this.editingContent?.rowID)!;
		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/owl/conversations/messages`, {
			method: 'PATCH',
			headers: {
				'Content-Type': 'application/json',
				'x-project-id': page.params.project_id ?? ''
			},
			body: JSON.stringify({
				conversation_id: page.params.conversation_id,
				row_id: this.editingContent.rowID,
				data: newContent
			})
		});
		const responseBody = await response.json();

		if (response.ok) {
			if (this.editingContent.columnID === 'User') {
				this.messages = Object.fromEntries(
					Object.entries(this.messages).map(([column, thread]) => [
						column,
						{
							...thread,
							thread: thread.thread.map((m) =>
								m.row_id === this.editingContent?.rowID && m.role === 'user'
									? {
											...m,
											content: Object.entries(newContent).map(([col, val]) =>
												col === 'User'
													? { type: 'text', text: newContent.User }
													: { type: 'input_s3', uri: val, column_name: col }
											),
											user_prompt: newContent.User
										}
									: m
							)
						}
					])
				);
			} else {
				this.messages = {
					[this.editingContent.columnID]: {
						...this.messages[this.editingContent.columnID],
						thread: this.messages[this.editingContent.columnID].thread.map((v) =>
							v.row_id === this.editingContent?.rowID
								? {
										...v,
										content: Object.entries(newContent).map(([col, val]) =>
											col === this.editingContent?.columnID
												? { type: 'text', text: newContent[this.editingContent.columnID] }
												: { type: 'input_s3', uri: val, column_name: col }
										)
									}
								: v
						)
					}
				};
			}
			// editingMessage[this.editingContent.columnID] = newContent;
			this.editingContent = null;
		} else {
			logger.error('CHAT_MESSAGE_EDIT', responseBody);
			toast.error('Failed to edit message', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}

		this.getMessages();
	}

	resetChat() {
		this.conversation = null;
		this.loadingConversation = true;
		this.messages = {};
		this.loadingMessages = true;
		this.currentOffsetMessages = 0;
		this.moreMessagesFinished = false;
		this.uploadColumns = {};
	}

	private async parseStream(reader: ReadableStreamDefaultReader<string>, newMessage = false) {
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
								if (parsedEvent.event === 'metadata') {
									if (!page.params.conversation_id) {
										goto(
											`/chat/${page.url.searchParams.get('project_id')}/${encodeURIComponent(parsedEvent.data.conversation_id)}`
										);
										setTimeout(() => chatState.refetchConversations(), 5000);
									}

									this.conversation = parsedEvent.data;
								}
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
										if (!this.reasoningContentStreams[streamDataRowID]) {
											this.reasoningContentStreams[streamDataRowID] = {};
										}

										if (
											!this.reasoningContentStreams[streamDataRowID][
												parsedEvent.data.output_column_name
											]
										) {
											this.reasoningContentStreams[streamDataRowID][
												parsedEvent.data.output_column_name
											] = '';
										}

										this.reasoningContentStreams[streamDataRowID][
											parsedEvent.data.output_column_name
										] += parsedEvent.data.choices[0]?.message?.reasoning_content ?? '';
									}

									if (parsedEvent.data.choices[0]?.message?.content) {
										if (this.loadedStreams[streamDataRowID][parsedEvent.data.output_column_name]) {
											if (renderCount++ >= 20) {
												this.loadedStreams[streamDataRowID][parsedEvent.data.output_column_name] = [
													...this.loadedStreams[streamDataRowID][
														parsedEvent.data.output_column_name
													],
													this.latestStreams[streamDataRowID][parsedEvent.data.output_column_name] +
														(parsedEvent.data.choices[0]?.message?.content ?? '')
												];
												this.latestStreams[streamDataRowID][parsedEvent.data.output_column_name] =
													'';
											} else {
												this.latestStreams[streamDataRowID][parsedEvent.data.output_column_name] +=
													parsedEvent.data.choices[0]?.message?.content ?? '';
											}
										}
									}

									/** Stream output details dialog */
									if (
										this.showOutputDetails.activeCell?.rowID === streamDataRowID &&
										this.showOutputDetails.activeCell?.columnID ===
											parsedEvent.data.output_column_name
									) {
										this.showOutputDetails = {
											...this.showOutputDetails,
											message: {
												chunks: this.showOutputDetails.message?.chunks ?? [],
												error: this.showOutputDetails.message?.error ?? null,
												content:
													(this.showOutputDetails.message?.content ?? '') +
													(parsedEvent.data.choices[0].message.content ?? '')
											},
											reasoningContent:
												(this.showOutputDetails.reasoningContent ?? '') +
												(parsedEvent.data.choices[0].message.reasoning_content ?? '')
										};
									}

									this.scrollChatToBottom();
								}
							} else if (parsedEvent.data.object === 'gen_table.references') {
								rowID = parsedEvent.data.row_id;
								const streamDataRowID = newMessage ? 'new' : rowID;

								this.loadedReferences = {
									...(this.loadedReferences ?? {}),
									[streamDataRowID]: {
										...((this.loadedReferences ?? {})[streamDataRowID] ?? {}),
										[parsedEvent.data.output_column_name]:
											parsedEvent.data as unknown as ChatReferences
									}
								};

								/** Add references to output details if active */
								if (
									this.showOutputDetails.activeCell?.rowID === streamDataRowID &&
									this.showOutputDetails.activeCell?.columnID ===
										parsedEvent.data.output_column_name
								) {
									this.showOutputDetails = {
										...this.showOutputDetails,
										message: {
											chunks: (parsedEvent.data as unknown as ChatReferences).chunks ?? [],
											error: this.showOutputDetails.message?.error ?? null,
											content: this.showOutputDetails.message?.content ?? ''
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

	async getConversations() {
		if (!page.params.project_id && !page.url.searchParams.has('project_id')) return;

		this.fetchController?.abort('Duplicate');
		this.fetchController = new AbortController();

		try {
			// autoAnimateController?.disable();
			this.isLoadingMoreConvs = true;

			const searchParams = new URLSearchParams([
				['offset', this.currentOffsetConvs.toString()],
				['limit', this.limitConvs.toString()],
				['order_by', 'updated_at'],
				['order_ascending', 'false']
				// ['organization_id', $activeOrganization.id]
			]);

			if (this.searchQuery.trim() !== '') {
				searchParams.append('search_query', this.searchQuery.trim());
			}

			const response = await fetch(
				`${PUBLIC_JAMAI_URL}/api/owl/conversations/list?${searchParams}`,
				{
					credentials: 'same-origin',
					signal: this.fetchController.signal,
					headers: {
						'x-project-id': page.params.project_id || page.url.searchParams.get('project_id')!
					}
				}
			);
			this.currentOffsetConvs += this.limitConvs;

			if (response.status == 200) {
				const moreProjects = await response.json();
				if (moreProjects.items.length) {
					this.conversations = [...this.conversations, ...moreProjects.items];
				} else {
					//* Finished loading oldest conversation
					this.moreConvsFinished = true;
				}
			} else {
				const responseBody = await response.json();
				console.error(responseBody);
				toast.error('Failed to fetch conversations', {
					id: responseBody?.message || JSON.stringify(responseBody),
					description: CustomToastDesc as any,
					componentProps: {
						description: responseBody?.message || JSON.stringify(responseBody),
						requestID: responseBody?.request_id
					}
				});
				this.loadingConvsError = {
					status: response.status,
					message: responseBody
				};
			}

			this.isLoadingMoreConvs = false;
		} catch (err) {
			//* don't show abort errors in browser
			if (err !== 'Duplicate') {
				console.error(err);
			}
		}
	}

	async editConversationTitle(
		newTitle: string,
		conversationID: string,
		projectID: string,
		successCb: () => void
	) {
		const response = await fetch(
			`${PUBLIC_JAMAI_URL}/api/owl/conversations/title?${new URLSearchParams([
				['conversation_id', conversationID],
				['title', newTitle ?? '']
			])}`,
			{
				method: 'PATCH',
				headers: {
					'x-project-id': projectID
				}
			}
		);
		const responseBody = await response.json();

		if (response.ok) {
			successCb();
		} else {
			logger.error('CHAT_TITLE_EDIT', responseBody);
			toast.error('Failed to edit conversation title', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc as any,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});
		}
	}

	async refetchConversations() {
		this.fetchController?.abort('Duplicate');
		this.conversations = [];
		this.currentOffsetConvs = 0;
		this.moreConvsFinished = false;
		await tick();
		this.getConversations();
		this.isLoadingSearch = false;
	}

	closeOutputDetails() {
		this.showOutputDetails = { ...this.showOutputDetails, open: false };
	}

	async scrollChatToBottom() {
		if (!browser || !this.chatWindow) return;

		if (
			this.chatWindow.scrollHeight - this.chatWindow.clientHeight - this.chatWindow.scrollTop <
				100 ||
			!this.generationStatus
		) {
			await tick();
			await tick();
			this.chatWindow.scrollTop = this.chatWindow.scrollHeight;
		}
	}
}

export const chatState = new ChatState();
