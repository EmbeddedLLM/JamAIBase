import type { ModelConfig, OrganizationReadRes, Project, UploadQueue } from '$lib/types';
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
export const modelConfigSort = persisted<SortOptions & { filter: string }>(
	'modelConfigSort',
	{ orderBy: 'created_at', order: 'desc', filter: 'all' },
	{ serializer }
);
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

export const modelsAvailable = writable<ModelConfig[]>([]);

export const uploadQueue = writable<UploadQueue>({
	activeFile: null,
	progress: 0,
	queue: []
});
export const uploadController = writable<AbortController | null>(null);

//* Non-local
function createActiveOrgStore() {
	const { subscribe, set, update } = writable<OrganizationReadRes | null>(null);

	return {
		subscribe,
		set,
		update,
		setOrgCookie: (id: string | null) => {
			if (id) {
				document.cookie = `activeOrganizationId=${id}; path=/; max-age=604800; samesite=strict`;
			} else {
				document.cookie = `activeOrganizationId=; path=/; max-age=604800; samesite=strict`;
			}
		}
	};
}
export const activeOrganization = createActiveOrgStore();
export const activeProject = writable<Project | null>(null);
export const loadingProjectData = writable<{ loading: boolean; error?: string }>({
	loading: true,
	error: undefined
});
