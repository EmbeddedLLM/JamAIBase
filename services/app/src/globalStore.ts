import type { AvailableModel, Organization, Project, UploadQueue } from '$lib/types';
import { serializer } from '$lib/utils';
import { persisted } from 'svelte-persisted-store';
import { writable } from 'svelte/store';

export const showLoadingOverlay = writable(false);
export const showDock = persisted<boolean>('dockopen', true, { serializer });
export const showRightDock = persisted<boolean>('rightdockopen', false, { serializer });
export const preferredTheme = persisted<'LIGHT' | 'DARK' | 'SYSTEM'>('theme', 'LIGHT', {
	serializer
});

type SortOptions = {
	orderBy: string;
	order: 'asc' | 'desc';
};
export const projectSort = persisted<SortOptions>(
	'projectSort',
	{ orderBy: 'updated_at', order: 'desc' },
	{ serializer }
);
export const aTableSort = persisted<SortOptions>(
	'aTableSort',
	{ orderBy: 'updated_at', order: 'desc' },
	{ serializer }
);
export const kTableSort = persisted<SortOptions>(
	'kTableSort',
	{ orderBy: 'updated_at', order: 'desc' },
	{ serializer }
);
export const cTableSort = persisted<SortOptions>(
	'cTableSort',
	{ orderBy: 'updated_at', order: 'desc' },
	{ serializer }
);

export const modelsAvailable = writable<AvailableModel[]>([]);

export const uploadQueue = writable<UploadQueue>({
	activeFile: null,
	progress: 0,
	queue: []
});
export const uploadController = writable<AbortController | null>(null);

//* Non-local
export const activeOrganization = writable<Organization | null>(null);
export const activeProject = writable<Project | null>(null);
export const loadingProjectData = writable<{ loading: boolean; error?: string }>({
	loading: true,
	error: undefined
});
