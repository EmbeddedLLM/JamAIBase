<script lang="ts" generics="T">
	import autoAnimate, {
		type AutoAnimateOptions,
		type AutoAnimationPlugin
	} from '@formkit/auto-animate';

	export let tagName: keyof HTMLElementTagNameMap = 'div';
	let className: string | undefined | null = undefined;
	export { className as class };
	export let itemList: T[];
	export let animateConfig: Partial<AutoAnimateOptions> | AutoAnimationPlugin = { duration: 100 };

	let dragHandle: HTMLElement | null;
	let dragMouseCoords: {
		x: number;
		y: number;
		startX: number;
		startY: number;
		width: number;
	} | null;
	let draggingItem: T | null;
	let draggingItemIndex: number | null;
	let hoveredItemIndex: number | null;

	$: if (
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
	<slot name="leading" />

	{#each itemList as item, itemIndex (item)}
		<slot
			name="list-item"
			{item}
			{itemIndex}
			{dragStart}
			{dragMove}
			{dragOver}
			{dragEnd}
			{dragMouseCoords}
			{draggingItem}
			{draggingItemIndex}
		/>
	{/each}

	<slot name="trailing" {dragMouseCoords} {draggingItem} />
</svelte:element>

<slot name="dragged-item" {dragMouseCoords} {draggingItem} />
