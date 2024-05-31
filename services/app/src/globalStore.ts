import { writable } from 'svelte/store';
import { persisted } from 'svelte-persisted-store';
import { serializer } from '$lib/utils';
import type { AvailableModel, Organization, UploadQueue } from '$lib/types';

export const showLoadingOverlay = writable(false);
export const showDock = persisted<boolean>('dockopen', true, { serializer });
export const showRightDock = persisted<boolean>('rightdockopen', true, { serializer });
export const preferredTheme = persisted<'LIGHT' | 'DARK' | 'SYSTEM'>('theme', 'LIGHT', {
	serializer
});

export const modelsAvailable = writable<AvailableModel[]>([]);

export const uploadQueue = writable<UploadQueue>({
	activeFile: null,
	progress: 0,
	queue: []
});
export const uploadController = writable<AbortController | null>(null);

//* Non-local
export const activeOrganization = writable<Organization | null>(null);
