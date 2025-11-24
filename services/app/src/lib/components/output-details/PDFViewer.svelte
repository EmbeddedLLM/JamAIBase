<script lang="ts">
	import * as pdfjs from 'pdfjs-dist';
	import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
	import 'pdfjs-dist/web/pdf_viewer.css';
	import MiniSearch from 'minisearch';
	import debounce from 'lodash/debounce';
	import type { ChatThread } from '$lib/types';

	import { Button } from '$lib/components/ui/button';
	import OpenIcon from '$lib/icons/OpenIcon.svelte';
	import AddIcon from '$lib/icons/AddIcon.svelte';

	export let docUrl: string;
	export let previewPage: number | undefined = undefined;
	export let previewChunk:
		| NonNullable<ChatThread['thread'][number]['references']>['chunks'][number]
		| null = null;

	let pdfDoc: pdfjs.PDFDocumentProxy;

	const minScale = 1.0;
	const maxScale = 5;
	let scale = 1.1;
	let scaleRes = 1.5;

	let pages: HTMLCanvasElement[] = [];
	let pageTexts: HTMLDivElement[] = [];
	let textLayers: pdfjs.TextLayer[] = [];

	let currentPage = 1;

	//@ts-ignore
	pdfjs.GlobalWorkerOptions.workerSrc = pdfjsWorker;

	const loadDocument = () => {
		const loadingTask = pdfjs.getDocument(`${docUrl}`);
		loadingTask.promise
			.then((doc) => {
				pdfDoc = doc;
				const numPages = doc.numPages;

				//* Create canvas elements
				for (let index = 0; index < (previewPage ? 3 : numPages); index++) {
					pages[index] = document.createElement('canvas');
				}

				let lastPromise;
				lastPromise = doc.getMetadata().then(function (data) {
					// console.log('## Info')
					// console.log(JSON.stringify(data.info, null, 2))
					// console.log()
					// if (data.metadata) {
					// 	console.log('## Metadata')
					// 	console.log(JSON.stringify(data.metadata.getAll(), null, 2))
					// 	console.log()
					// }
				});

				// Loading of the first page will wait on metadata and subsequent loadings
				// will wait on the previous pages.
				for (let i = 1; i <= numPages; i++) {
					if (previewPage) {
						if (i < previewPage - 1 || i > previewPage + 1) {
							continue;
						}

						lastPromise = lastPromise.then(loadPage.bind(null, i, i - previewPage + 1));
					} else {
						lastPromise = lastPromise.then(loadPage.bind(null, i, i));
					}
				}
				return lastPromise;
			})
			.then(
				() => {
					onFinishLoad();
				},
				(err) => {
					//* Not sure what this is
					if (!(err instanceof Error && err.message.startsWith('Setting up fake worker failed:'))) {
						console.error('Error: ' + err);
					}
				}
			);
	};
	loadDocument();

	const loadPage = (pageNum: number, index: number) => {
		return pdfDoc
			.getPage(pageNum)
			.then((page) => {
				const viewport = page.getViewport({ scale: scaleRes });

				if (!pages[index]) return;

				const context = pages[index].getContext('2d');
				pages[index].style.width = `${(viewport.width / scaleRes) * scale}px`;
				pages[index].style.height = `${(viewport.height / scaleRes) * scale}px`;
				pages[index].height = viewport.height;

				pages[index].width = viewport.width;

				const renderContext = {
					canvasContext: context!,
					viewport: viewport
				};

				// Render PDF page
				const renderTask = page.render(renderContext);
				renderTask.promise
					.then(() => page.getTextContent())
					.then((textContent) => {
						if (!pageTexts[index]) return;

						// Assign CSS to the textLayer element
						pageTexts[index].style.left = pages[index].offsetLeft + 'px';
						pageTexts[index].style.top = pages[index].offsetTop + 'px';
						pageTexts[index].style.height = pages[index].offsetHeight + 'px';
						pageTexts[index].style.width = pages[index].offsetWidth + 'px';

						// Pass the data to the method for rendering of text over the pdf canvas.
						if (textLayers[index]) {
							// FIXME: text layers misalign on scaling :(, check styling above
							console.log(index, textLayers[index]);
							textLayers[index].update({ viewport: page.getViewport({ scale }) });
						} else {
							textLayers[index] = new pdfjs.TextLayer({
								textContentSource: textContent,
								container: pageTexts[index],
								viewport: page.getViewport({ scale })
							});

							textLayers[index].render().then(() => {
								page.cleanup();
							});
						}
					});
			})
			.catch((err) => {
				//* Ignore invalid page request error
				if ((err as Error).message !== 'Invalid page request.') {
					console.error(err);
				}
			});
	};

	function onFinishLoad() {
		createObserver();
		if (previewChunk?.page && previewChunk.page !== null) {
			//* Scroll to target page
			pages[previewPage ? 1 : previewChunk.page].scrollIntoView({
				block: 'end',
				behavior: 'instant'
			});

			//TODO: This is a hacky way to wait for the text to load
			setTimeout(() => {
				if (previewChunk.text) {
					const pageTextsChildren = pageTexts.filter((i) => i).map((item) => item.childNodes);
					const pageTextsContent = pageTextsChildren.map((item) =>
						[...item].map((item) => item.textContent).join('')
					);

					const miniSearchFindPage = new MiniSearch({
						idField: 'index',
						fields: ['text'],
						storeFields: ['index']
					});
					miniSearchFindPage.addAll(pageTextsContent.map((text, index) => ({ text, index })));

					const result = miniSearchFindPage.search(previewChunk.text, { fuzzy: true });
					if (!result[0]) return;
					const resultIndex = result[0].index;

					//* Find the start and end of the preview text by closest match
					const pageChildrenArr = [...pageTextsChildren[resultIndex]];
					let groupedChildren: { startEl: ChildNode; endEl: ChildNode; text: string }[] = [];
					pageChildrenArr
						.filter((item) => item.nodeName == 'SPAN')
						.forEach((item, index) => {
							if (index % 2 === 0) {
								groupedChildren.push({
									startEl: item,
									endEl: item,
									text: item.textContent ?? ''
								});
							} else {
								groupedChildren[groupedChildren.length - 1].text += item.textContent;
								groupedChildren[groupedChildren.length - 1].endEl = item;
							}
						});

					const miniFindStartEnd = new MiniSearch({
						idField: 'startEl',
						fields: ['text'],
						storeFields: ['startEl', 'endEl']
					});
					miniFindStartEnd.addAll(groupedChildren);

					const startSearch = miniFindStartEnd.search(previewChunk.text.slice(0, 40), {
						fuzzy: true
					});
					const start = pageChildrenArr.findIndex((item) => item === startSearch[0].startEl);
					const endSearch = miniFindStartEnd.search(previewChunk.text.slice(-40), {
						fuzzy: true
					});
					const end = pageChildrenArr.findIndex((item) => item === endSearch[0].endEl);

					//* Get all elements between start and end
					const elements = pageChildrenArr.slice(Math.min(start, end), Math.max(start, end) + 1);

					//* Modify the elements to highlight the text
					elements.forEach((item) => {
						(item as HTMLElement).style.backgroundColor = '#95004833';
					});
				}
			}, 500);
		}
	}

	function createObserver() {
		const observer = new IntersectionObserver(
			(entries) => {
				entries.forEach((entry) => {
					if (entry.isIntersecting) {
						const intersectingPage =
							pages.findIndex((page) => page === entry.target) +
							1 +
							(previewPage ? -2 + previewPage : 0);
						//* Prevent currentPage from being 0 if previewed page is the first page
						currentPage = intersectingPage == 0 ? 1 : intersectingPage;
					}
				});
			},
			{ threshold: [0.5] }
		);

		pages.forEach((page) => {
			observer.observe(page);
		});
	}

	const onZoomIn = () => {
		if (scale <= maxScale) {
			scale += 0.25;
			reloadPages();
		}
	};

	const onZoomOut = () => {
		if (scale >= minScale) {
			scale -= 0.25;
			reloadPages();
		}
	};

	const reloadPages = debounce(() => {
		scaleRes = 4 * scale - 1.6;
		if (previewPage) {
			for (let index = -1; index < 2; index++) {
				loadPage(previewPage + index, index + 1);
			}
		} else {
			for (let index = 0; index < pages.length; index++) {
				loadPage(index + 1, index);
			}
		}
	}, 500);
</script>

<div class="flex h-full w-full grow flex-col">
	<div
		class="flex w-full items-center justify-between gap-3 bg-[#F9F9FA] px-6 py-2 data-dark:bg-[#38383D]"
	>
		<div>
			<span class="text-sm text-[#000] data-dark:text-[#AAA]">
				{previewPage ? 'Viewing page' : 'Page'}
			</span>
			<span class="text-sm text-[#000] data-dark:text-[#FFF]">
				{previewPage ? previewPage : currentPage}
			</span>
			<span class="text-sm text-[#000] data-dark:text-[#AAA]">{previewPage ? 'to' : '/'}</span>
			<span class="text-sm text-[#000] data-dark:text-[#FFF]">
				{previewPage ? previewPage + 1 : pages.length}
			</span>

			{#if previewPage}
				<span class="text-sm text-[#000] data-dark:text-[#AAA]">/</span>
				<span class="text-sm text-[#000] data-dark:text-[#AAA]">Page</span>
				<span class="text-sm text-[#000] data-dark:text-[#FFF]">{currentPage}</span>
			{/if}
		</div>

		<!-- <div class="flex gap-1">
			<Button
				variant="ghost"
				title="Zoom out"
				onclick={onZoomOut}
				class="aspect-square h-8 p-0 text-xl">–</Button
			>
			<Button
				variant="ghost"
				title="Zoom in"
				onclick={onZoomIn}
				class="aspect-square h-8 p-0 text-xl"
			>
				<AddIcon class="w-4" />
			</Button>
		</div> -->

		<Button
			variant="ghost"
			href={docUrl}
			target="_blank"
			class="flex h-8 w-max gap-2 rounded-md p-0 px-2 text-xs font-normal"
		>
			<OpenIcon class="w-3" />
			View document
		</Button>
	</div>

	<div class="flex h-[95%] flex-col gap-2 bg-[#D4D4D7] p-4 data-dark:bg-[#2A2A2E]">
		{#if pages.length}
			<div
				id="viewer"
				style={`--scale-factor: ${scale};`}
				class="pdfViewer overflow-auto !pb-[4.6rem]"
			>
				{#each pages as page, index}
					<div
						style={`width: ${(page?.width / scaleRes) * scale}px; height: ${
							(page?.height / scaleRes) * scale
						}px;`}
						class="page !my-4 !bg-transparent first:!mt-0 last:!mb-0"
					>
						<div class="canvasWrapper !overflow-visible">
							<canvas
								style={`width: ${(page?.width / scaleRes) * scale}px; height: ${
									(page?.height / scaleRes) * scale
								}px;`}
								bind:this={page}
							></canvas>
						</div>
						<div bind:this={pageTexts[index]} class="textLayer"></div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="flex h-full w-full grow flex-col items-center justify-center gap-2">
				<span class="loading loading-spinner loading-lg text-accent-2"></span>
			</div>
		{/if}
	</div>
</div>
