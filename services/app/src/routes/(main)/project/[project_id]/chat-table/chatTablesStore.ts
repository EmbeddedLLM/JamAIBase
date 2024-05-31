import { writable } from 'svelte/store';
import type { ActionTable } from '$lib/types';

export const pastChatAgents = writable<Omit<ActionTable, 'num_rows'>[]>([]);
export const pastChatConversations = writable<Omit<ActionTable, 'num_rows'>[]>([]);
