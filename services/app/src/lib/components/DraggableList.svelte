<script lang="ts" generics="T">
	import autoAnimate, {
		type AutoAnimateOptions,
		type AutoAnimationPlugin
	} from '@formkit/auto-animate';
	import type { Snippet } from 'svelte';

	interface Props {
		tagName?: keyof HTMLElementTagNameMap;
		class?: string | null;
		itemList: T[];
		animateConfig?: Partial<AutoAnimateOptions> | AutoAnimationPlugin;
		leading?: Snippet;
		trailing?: Snippet<
			[{ dragMouseCoords: typeof dragMouseCoords; draggingItem: typeof draggingItem }]
		>;
		listItem: Snippet<
			[
				{
					item: T;
					itemIndex: number;
					dragStart: typeof dragStart;
					dragMove: typeof dragMove;
					dragOver: typeof dragOver;
					dragEnd: typeof dragEnd;
					dragMouseCoords: typeof dragMouseCoords;
					draggingItem: typeof draggingItem;
					draggingItemIndex: typeof draggingItemIndex;
				}
			]
		>;
		draggedItem: Snippet<
			[{ dragMouseCoords: typeof dragMouseCoords; draggingItem: typeof draggingItem }]
		>;
	}

	let {
		tagName = 'div',
		class: className,
		itemList = $bindable(),
		animateConfig = { duration: 100 },
		leading,
		trailing,
		listItem,
		draggedItem
	}: Props = $props();

	let dragHandle: HTMLElement | null;
	let dragMouseCoords: {
		x: number;
		y: number;
		startX: number;
		startY: number;
		width: number;
	} | null = $state(null);
	let draggingItem: T | null = $state(null);
	let draggingItemIndex: number | null = $state(null);
	let hoveredItemIndex: number | null = $state(null);

	$effect(() => {
		if (
			draggingItemIndex != null &&
			hoveredItemIndex != null &&
			draggingItemIndex != hoveredItemIndex
		) {
			[itemList[draggingItemIndex], itemList[hoveredItemIndex]] = [
				itemList[hoveredItemIndex],
				itemList[draggingItemIndex]
			];

			draggingItemIndex = hoveredItemIndex;
		}
	});

	function dragOver(e: DragEvent, index: number) {
		if (draggingItemIndex !== null) {
			const rect = (e.target as HTMLDivElement).getBoundingClientRect();
			const y = e.clientY - rect.top;
			if ((draggingItemIndex < index && y > 22) || (draggingItemIndex > index && y < 22)) {
				hoveredItemIndex = index;
			}
		}
	}

	function dragStart(e: DragEvent | UIEvent, item: T, index: number, draggable = true) {
		// Prevent dragging on touch if draggable attribute is false
		if (!draggable) return;

		const isTouch = e instanceof UIEvent && 'touches' in e;
		if (isTouch && (e as TouchEvent).touches.length > 1) return;

		const clientX = isTouch ? (e as TouchEvent).touches[0].clientX : (e as DragEvent).clientX;
		const clientY = isTouch ? (e as TouchEvent).touches[0].clientY : (e as DragEvent).clientY;
		//@ts-ignore
		let rect = e.currentTarget.getBoundingClientRect();
		dragHandle = e.target as HTMLElement;
		dragMouseCoords = {
			x: clientX,
			y: clientY,
			startX: clientX - rect.left,
			startY: clientY - rect.top,
			//@ts-ignore
			width: e.currentTarget.parentElement.offsetWidth
		};
		draggingItem = item;
		draggingItemIndex = index;
	}

	let animationFrameId: ReturnType<typeof requestAnimationFrame> | null;
	function dragMove(e: DragEvent | TouchEvent) {
		if (animationFrameId) {
			cancelAnimationFrame(animationFrameId);
		}

		animationFrameId = requestAnimationFrame(() => {
			if (!draggingItem) return;
			const isTouch = e instanceof UIEvent && 'touches' in e;
			const clientX = isTouch ? e.touches[0].clientX : e.clientX;
			const clientY = isTouch ? e.touches[0].clientY : e.clientY;
			if (clientX === 0 && clientY === 0) return;
			if (isTouch) {
				let target = document.elementFromPoint(clientX, clientY);
				while (!target?.contains(dragHandle)) {
					if (target) {
						target.dispatchEvent(new DragEvent('dragover', { clientX, clientY }));
						target = target.parentElement;
					} else {
						break;
					}
				}
			}
			//@ts-ignore
			dragMouseCoords = { ...dragMouseCoords, x: clientX, y: clientY };

			animationFrameId = null;
		});
	}

	function dragEnd() {
		dragHandle = null;
		dragMouseCoords = null;
		draggingItem = null;
		draggingItemIndex = null;
		hoveredItemIndex = null;
	}
</script>

<svelte:element this={tagName} use:autoAnimate={animateConfig} class={className}>
	{@render leading?.()}

	{#each itemList as item, itemIndex (item)}
		{@render listItem({
			item,
			itemIndex,
			dragStart,
			dragMove,
			dragOver,
			dragEnd,
			dragMouseCoords,
			draggingItem,
			draggingItemIndex
		})}
	{/each}

	{@render trailing?.({ dragMouseCoords, draggingItem })}
</svelte:element>

{@render draggedItem({ dragMouseCoords, draggingItem })}
