import type { AvailableModel, Organization, UploadQueue } from '$lib/types';
import { serializer } from '$lib/utils';
import { persisted } from 'svelte-persisted-store';
import { writable } from 'svelte/store';

export const showLoadingOverlay = writable(false);
export const showDock = persisted<boolean>('dockopen', true, { serializer });
export const showRightDock = persisted<boolean>('rightdockopen', false, { serializer });
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
