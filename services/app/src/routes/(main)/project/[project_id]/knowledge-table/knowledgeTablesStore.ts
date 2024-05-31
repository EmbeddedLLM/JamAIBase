import { writable } from 'svelte/store';
import type { ActionTable } from '$lib/types';

export const pastKnowledgeTables = writable<Omit<ActionTable, 'num_rows'>[]>([]);
