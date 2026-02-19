import { modelLogos, userRoles } from '$lib/constants';
import type { ReferenceChunk } from '$lib/types';
import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChild<T> = T extends { child?: any } ? Omit<T, 'child'> : T;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChildren<T> = T extends { children?: any } ? Omit<T, 'children'> : T;
export type WithoutChildrenOrChild<T> = WithoutChildren<WithoutChild<T>>;
export type WithElementRef<T, U extends HTMLElement = HTMLElement> = T & {
	ref?: U | null;
};

//* Custom serializer for svelte-persisted-store
export const serializer = {
	parse: (text: string) => {
		try {
			return JSON.parse(text);
		} catch (e) {
			return text;
		}
	},
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	stringify: (object: any) => {
		try {
			return JSON.stringify(object);
		} catch (e) {
			return object;
		}
	}
};

export const enumerateObj = (obj: object) => {
	if (!obj) return obj;
	const newObj: Record<string, unknown> = {};
	const allProps = getAllProperties(obj);

	allProps.forEach((prop) => {
		if (prop in obj) {
			//@ts-expect-error Object
			if (obj[prop] === null) {
				newObj[prop] = null;
				return;
			}
			//@ts-expect-error Object
			if (typeof obj[prop] === 'object' && prop !== '__proto__') {
				//@ts-expect-error Object
				newObj[prop] = enumerateNonEnumerable(obj[prop]);
			} else {
				//@ts-expect-error Object
				newObj[prop] = obj[prop];
			}
		}
	});

	return newObj;
};

function getAllProperties(obj: object) {
	if (typeof obj !== 'object' && typeof obj !== 'function') return [];
	const allProps: string[] = [];
	let curr = obj;
	do {
		const props = Object.getOwnPropertyNames(curr);
		props.forEach(function (prop) {
			if (allProps.indexOf(prop) === -1) allProps.push(prop);
		});
	} while ((curr = Object.getPrototypeOf(curr)));
	return allProps;
}

export function hasPermission(
	user: App.Locals['user'],
	ossMode: boolean,
	organizationId: string,
	projectId: string,
	_orgRole?: (typeof userRoles)[number],
	_projRole?: (typeof userRoles)[number]
) {
	if (ossMode) return true;

	const roleHierarchy = {
		GUEST: 1,
		MEMBER: 2,
		ADMIN: 3
	} as Record<(typeof userRoles)[number], number>;

	const orgRole = user?.org_memberships.find((org) => org.organization_id === organizationId)?.role;
	const projRole = user?.proj_memberships.find((proj) => proj.project_id === projectId)?.role;

	const userOrgLevel = roleHierarchy[orgRole ?? 'GUEST'];
	const userProjLevel = roleHierarchy[projRole ?? 'GUEST'];

	const reqOrgLevel = roleHierarchy[_orgRole ?? 'GUEST'];
	const reqProjLevel = roleHierarchy[_projRole ?? 'GUEST'];
	if ((!_orgRole || userOrgLevel >= reqOrgLevel) && (!_projRole || userProjLevel >= reqProjLevel)) {
		return true;
	} else {
		return false;
	}
}

export function insertAtCursor(el: HTMLInputElement | HTMLTextAreaElement, value: string) {
	//IE support
	//@ts-expect-error Support
	if (document && document.selection) {
		el.focus();
		//@ts-expect-error Support
		const sel = document.selection.createRange();
		sel.text = value;
	}
	//MOZILLA and others
	else if (el.selectionStart || el.selectionStart == 0) {
		const startPos = el.selectionStart;
		const endPos = el.selectionEnd ?? 0;
		el.value =
			el.value.substring(0, startPos) + value + el.value.substring(endPos, el.value.length);
		el.selectionStart = startPos + value.length;
		el.selectionEnd = startPos + value.length;
	} else {
		el.value += value;
	}
}

export function textToFileDownload(filename: string, data: string | Blob) {
	const blob = typeof data === 'string' ? new Blob([data], { type: 'text/csv' }) : data;
	//@ts-expect-error IE support
	if (window.navigator.msSaveOrOpenBlob) {
		//@ts-expect-error IE support
		window.navigator.msSaveBlob(blob, filename);
	} else {
		const elem = window.document.createElement('a');
		elem.href = window.URL.createObjectURL(blob);
		elem.download = filename;
		document.body.appendChild(elem);
		elem.click();
		document.body.removeChild(elem);
	}
}

export function extendArray<T>(arr: T[], length: number, fillWith: any = ''): T[] {
	return arr.concat(Array(Math.max(0, length - arr.length)).fill(fillWith));
}

export function isValidUri(string: string): URL | null {
	let url: URL;

	try {
		url = new URL(string);
	} catch (_) {
		return null;
	}

	return url;
}

/** Only use to escape HTML inner text (no attributes) */
export function escapeHtmlText(unsafe: string): string {
	return unsafe
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#039;');
}

export function getModelIcon(icon: any) {
	const modelKey = (icon && icon in modelLogos ? icon : 'generic') as keyof typeof modelLogos;
	return {
		src: modelLogos[modelKey].src,
		alt: modelLogos[modelKey].title
	};
}

export function waitForElement(selector: string) {
	return new Promise<Element | null>((resolve) => {
		if (document.querySelector(selector)) {
			return resolve(document.querySelector(selector));
		}

		const observer = new MutationObserver(() => {
			if (document.querySelector(selector)) {
				observer.disconnect();
				resolve(document.querySelector(selector));
			}
		});

		// If you get "parameter 1 is not of type 'Node'" error, see https://stackoverflow.com/a/77855838/492336
		observer.observe(document.body, {
			childList: true,
			subtree: true
		});
	});
}

export function citationReplacer(
	match: string,
	word: string,
	columnID: string,
	rowID: string,
	chunks: ReferenceChunk[]
) {
	const citationIndices = match.match(/@(\d+)/g)?.map((m) => m.substring(1)) ?? [];
	return citationIndices
		.map(
			(idx) =>
				`<button 
						data-column="${columnID}" 
						data-row="${rowID}" 
						data-citation="${chunks[Number(idx)]?.chunk_id ?? ''}" 
						class="citation-btn aspect-square h-5 w-5 rounded-full bg-[#FFD8DF] text-xs text-[#475467]"
					>${Number(idx) + 1}</button>`
		)
		.join(' ');
}
