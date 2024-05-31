import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { cubicOut } from 'svelte/easing';
import type { TransitionConfig } from 'svelte/transition';

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

type FlyAndScaleParams = {
	y?: number;
	x?: number;
	start?: number;
	duration?: number;
};

export const flyAndScale = (
	node: Element,
	params: FlyAndScaleParams = { y: -8, x: 0, start: 0.95, duration: 150 }
): TransitionConfig => {
	const style = getComputedStyle(node);
	const transform = style.transform === 'none' ? '' : style.transform;

	const scaleConversion = (valueA: number, scaleA: [number, number], scaleB: [number, number]) => {
		const [minA, maxA] = scaleA;
		const [minB, maxB] = scaleB;

		const percentage = (valueA - minA) / (maxA - minA);
		const valueB = percentage * (maxB - minB) + minB;

		return valueB;
	};

	const styleToString = (style: Record<string, number | string | undefined>): string => {
		return Object.keys(style).reduce((str, key) => {
			if (style[key] === undefined) return str;
			return str + `${key}:${style[key]};`;
		}, '');
	};

	return {
		duration: params.duration ?? 200,
		delay: 0,
		css: (t) => {
			const y = scaleConversion(t, [0, 1], [params.y ?? 5, 0]);
			const x = scaleConversion(t, [0, 1], [params.x ?? 0, 0]);
			const scale = scaleConversion(t, [0, 1], [params.start ?? 0.95, 1]);

			return styleToString({
				transform: `${transform} translate3d(${x}px, ${y}px, 0) scale(${scale})`,
				opacity: t
			});
		},
		easing: cubicOut
	};
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
