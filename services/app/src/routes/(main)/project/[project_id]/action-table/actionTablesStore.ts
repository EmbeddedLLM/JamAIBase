import { writable } from 'svelte/store';
import type { ActionTable } from '$lib/types';

export const pastActionTables = writable<Omit<ActionTable, 'num_rows'>[]>([]);
