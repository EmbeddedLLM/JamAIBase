<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import toUpper from 'lodash/toUpper';
	import { page } from '$app/stores';
	import { genTableRows, tableState } from '$lib/components/tables/tablesStore';
	import { cn } from '$lib/utils';
	import logger from '$lib/logger';
	import type { GenTable, GenTableStreamEvent } from '$lib/types';

	import StarIcon from '$lib/icons/StarIcon.svelte';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button, type Props, type Events } from '$lib/components/ui/button';

	type $$Props = Props & {
		tableType: 'action' | 'knowledge' | 'chat';
		tableData: GenTable | undefined;
		refetchTable: () => void;
	};
	type $$Events = Events;

	let className: $$Props['class'] = undefined;
	export { className as class };
	export let tableType: $$Props['tableType'];
	export let tableData: $$Props['tableData'];
	export let refetchTable: $$Props['refetchTable'];

	const keyframes = [
		{
			paths: [
				'M37.0879 39.9598C50.0807 34.4186 43.0531 29.6566 30.0603 4.46149C23.0327 -0.213899 9.87647 -2.63817 2.44032 4.46149C-4.99582 11.5612 6.9347 23.7691 6.9347 33.6394C6.9347 43.5096 24.095 45.501 37.0879 39.9598Z',
				'M41.5559 29.9716C32.6897 29.4666 29.1067 16.6851 34.6329 7.47777C40.0201 -1.49796 44.5994 4.14651 65.361 2.1687C60.3814 4.47411 98.2753 7.47777 93.5993 10.3138C88.9233 13.1498 67.0007 19.5211 61.4745 21.8132C55.9483 24.1053 50.4221 30.4767 41.5559 29.9716Z',
				'M45.9221 39.2166C38.6265 31.7087 46.2614 32.4661 54.9144 22.3897C55.2763 23.8935 56.835 25.4917 60.174 19.8542C64.3478 12.8073 68.5216 17.2857 75.0028 18.8004C81.484 20.3152 86.1328 22.3897 85.9971 29.7659C85.8614 37.142 82.6038 35.9236 75.0028 39.2166C67.4018 42.5095 69.4377 44.0242 60.174 46.1317C50.9103 48.2392 53.2177 46.7244 45.9221 39.2166Z'
			],
			colors: ['#A0D7FF', '#4169E1', '#ED00D5']
		},
		{
			paths: [
				'M24.4816 47.9597C38.3359 49.4465 34.5248 42.0046 35.2579 14.2237C31.4057 6.85595 21.1906 -1.52338 11.397 0.986263C1.60347 3.4959 6.11637 19.6574 1.43197 28.1012C-3.25243 36.5449 10.6273 46.473 24.4816 47.9597Z',
				'M14.8431 62.0029C6.11994 61.4978 2.59481 48.7163 8.03187 39.509C13.3322 30.5333 17.8376 36.1778 38.2644 34.1999C33.365 36.5054 70.6478 39.509 66.0472 42.345C61.4466 45.181 39.8776 51.5524 34.4405 53.8445C29.0034 56.1366 23.5664 62.5079 14.8431 62.0029Z',
				'M41.4315 36.9967C33.9662 29.2467 41.7787 30.0285 50.6329 19.6271C51.0032 21.1794 52.5981 22.8291 56.0148 17.0098C60.2856 9.73558 64.5565 14.3584 71.1884 15.922C77.8204 17.4856 82.5773 19.6271 82.4384 27.2412C82.2996 34.8553 78.9662 33.5976 71.1884 36.9967C63.4106 40.3959 65.494 41.9595 56.0148 44.135C46.5356 46.3104 48.8967 44.7468 41.4315 36.9967Z'
			],
			colors: ['#EE8698', '#A0D7FF', '#ED00D5']
		},
		{
			paths: [
				'M21.9178 42.4286C34.2974 43.7571 30.892 37.1074 31.547 12.2838C28.1049 5.70033 18.9772 -1.78701 10.2261 0.455473C1.47511 2.69796 5.50761 17.1391 1.32186 24.684C-2.86388 32.2289 9.53831 41.1001 21.9178 42.4286Z',
				'M10.7889 31.9676C0.778643 31.3904 -3.26659 16.783 2.97267 6.26031C9.05499 -3.99767 14.2251 2.45316 37.6657 0.192796C32.0435 2.82756 74.827 6.26031 69.5476 9.50147C64.2682 12.7426 39.5169 20.0241 33.2776 22.6437C27.0384 25.2633 20.7991 32.5448 10.7889 31.9676Z',
				'M16.126 45.7144C8.32135 37.7222 16.489 38.5284 25.7456 27.802C26.1328 29.4028 27.8002 31.104 31.3722 25.1028C35.8372 17.6013 40.3021 22.3686 47.2355 23.9811C54.1689 25.5936 59.1421 27.802 58.9969 35.654C58.8517 43.506 55.3668 42.209 47.2355 45.7144C39.1042 49.2198 41.2822 50.8323 31.3722 53.0757C21.4621 55.3191 23.9306 53.7067 16.126 45.7144Z'
			],
			colors: ['#EE8698', '#A0D7FF', '#ED00D5']
		}
	];

	async function handleRegenRow() {
		if (!tableData || !$genTableRows) return;
		if (Object.keys($tableState.streamingRows).length !== 0) return;

		const toRegenRowIds = $tableState.selectedRows.filter((i) => !$tableState.streamingRows[i]);
		if (toRegenRowIds.length === 0)
			return toast.info('Select a row to start generating', { id: 'row-select-req' });
		tableState.setSelectedRows([]);

		tableState.addStreamingRows(
			toRegenRowIds.reduce(
				(acc, curr) => ({
					...acc,
					[curr]: tableData.cols.filter((col) => col.gen_config).map((col) => col.id)
				}),
				{}
			)
		);

		//? Optimistic update, clear row
		const originalValues = toRegenRowIds.map((toRegenRowId) => ({
			id: toRegenRowId,
			value: $genTableRows!.find((row) => row.ID === toRegenRowId)!
		}));
		genTableRows.clearOutputs(tableData, toRegenRowIds);

		const response = await fetch(`${PUBLIC_JAMAI_URL}/api/v1/gen_tables/${tableType}/rows/regen`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				table_id: $page.params.table_id,
				row_ids: toRegenRowIds,
				stream: true
			})
		});

		if (response.status != 200) {
			const responseBody = await response.json();
			logger.error(toUpper(`${tableType}TBL_ROW_REGEN`), responseBody);
			console.error(responseBody);
			toast.error('Failed to regenerate rows', {
				id: responseBody.message || JSON.stringify(responseBody),
				description: CustomToastDesc,
				componentProps: {
					description: responseBody.message || JSON.stringify(responseBody),
					requestID: responseBody.request_id
				}
			});

			//? Revert back to original value
			genTableRows.revert(originalValues);
		} else {
			const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();

			let isStreaming = true;
			let lastMessage = '';
			while (isStreaming) {
				try {
					const { value, done } = await reader.read();
					if (done) break;

					if (value.endsWith('\n\n')) {
						const lines = (lastMessage + value)
							.split('\n\n')
							.filter((i) => i.trim())
							.flatMap((line) => line.split('\n')); //? Split by \n to handle collation

						lastMessage = '';

						for (const line of lines) {
							const sumValue = line.replace(/^data: /, '').replace(/data: \[DONE\]\s+$/, '');

							if (sumValue.trim() == '[DONE]') break;

							let parsedValue;
							try {
								parsedValue = JSON.parse(sumValue) as GenTableStreamEvent;
							} catch (err) {
								console.error('Error parsing:', sumValue);
								logger.error(toUpper(`${tableType}TBL_ROW_REGENSTREAMPARSE`), {
									parsing: sumValue,
									error: err
								});
								continue;
							}

							if (parsedValue.object === 'gen_table.completion.chunk') {
								if (parsedValue.choices[0].finish_reason) {
									switch (parsedValue.choices[0].finish_reason) {
										case 'error': {
											logger.error(toUpper(`${tableType}_ROW_ADDSTREAM`), parsedValue);
											console.error('STREAMING_ERROR', parsedValue);
											alert(`Error while streaming: ${parsedValue.choices[0].message.content}`);
											break;
										}
										default: {
											const streamingCols = $tableState.streamingRows[parsedValue.row_id].filter(
												(col) => col !== parsedValue.output_column_name
											);
											if (streamingCols.length === 0) {
												tableState.delStreamingRows([parsedValue.row_id]);
											} else {
												tableState.addStreamingRows({
													[parsedValue.row_id]: streamingCols
												});
											}
											break;
										}
									}
								} else {
									//* Add chunk to active row'
									genTableRows.stream(
										parsedValue.row_id,
										parsedValue.output_column_name,
										parsedValue.choices[0].message.content ?? ''
									);
								}
							} else {
								console.log('Unknown message:', parsedValue);
							}
						}
					} else {
						lastMessage += value;
					}
				} catch (err) {
					// logger.error(toUpper(`${tableType}TBL_ROW_REGENSTREAM`), err);
					console.error(err);

					//? Below necessary for retry
					tableState.delStreamingRows(toRegenRowIds);

					refetchTable();

					throw err;
				}
			}

			refetchTable();
		}

		tableState.delStreamingRows(toRegenRowIds);

		refetchTable();
	}

	let generateBtnSvg: SVGSVGElement;
	$: if (generateBtnSvg) {
		const shapes = generateBtnSvg.querySelectorAll('path');

		let currentKeyframe = 0;

		function animate() {
			const frame = keyframes[currentKeyframe];

			shapes.forEach((shape, index) => {
				shape?.setAttribute('d', frame.paths[index]);
				shape?.setAttribute('fill', frame.colors[index]);
			});

			currentKeyframe = (currentKeyframe + 1) % keyframes.length;
		}

		animate();
		setInterval(animate, 1400);
	}
</script>

<Button
	{...$$restProps}
	title="Generate"
	on:click={handleRegenRow}
	class={cn(
		`relative pl-0 sm:pl-2.5 pr-0 sm:pr-3.5 py-0 h-8 sm:h-9 w-min aspect-square sm:aspect-auto font-normal overflow-hidden transition-colors group/gen-btn`,
		className
	)}
>
	<svg
		bind:this={generateBtnSvg}
		width="94"
		height="47"
		viewBox="0 0 94 47"
		fill="none"
		xmlns="http://www.w3.org/2000/svg"
		class="absolute top-0 left-0 h-full w-full z-0 bg-[#232324] scale-[2] translate-x-3.5 -translate-y-1.5 [&_path]:transition-all [&_path]:[transition-duration:3s]"
	>
		<g style="mix-blend-mode: color-dodge" filter="url(#filter0_f_4380_34276)">
			<path
				id="shape1"
				d="M37.0879 39.9598C50.0807 34.4186 43.0531 29.6566 30.0603 4.46149C23.0327 -0.213899 9.87647 -2.63817 2.44032 4.46149C-4.99582 11.5612 6.9347 23.7691 6.9347 33.6394C6.9347 43.5096 24.095 45.501 37.0879 39.9598Z"
				fill="#A0D7FF"
			/>
			<path
				id="shape2"
				d="M41.5559 29.9716C32.6897 29.4666 29.1067 16.6851 34.6329 7.47777C40.0201 -1.49796 44.5994 4.14651 65.361 2.1687C60.3814 4.47411 98.2753 7.47777 93.5993 10.3138C88.9233 13.1498 67.0007 19.5211 61.4745 21.8132C55.9483 24.1053 50.4221 30.4767 41.5559 29.9716Z"
				fill="#4169E1"
			/>
			<path
				id="shape3"
				d="M45.9221 39.2166C38.6265 31.7087 46.2614 32.4661 54.9144 22.3897C55.2763 23.8935 56.835 25.4917 60.174 19.8542C64.3478 12.8073 68.5216 17.2857 75.0028 18.8004C81.484 20.3152 86.1328 22.3897 85.9971 29.7659C85.8614 37.142 82.6038 35.9236 75.0028 39.2166C67.4018 42.5095 69.4377 44.0242 60.174 46.1317C50.9103 48.2392 53.2177 46.7244 45.9221 39.2166Z"
				fill="#ED00D5"
			/>
		</g>
		<defs>
			<filter
				id="filter0_f_4380_34276"
				x="-30"
				y="-26"
				width="134"
				height="87"
				filterUnits="userSpaceOnUse"
				color-interpolation-filters="sRGB"
			>
				<feFlood flood-opacity="0" result="BackgroundImageFix" />
				<feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape" />
				<feGaussianBlur stdDeviation="9" result="effect1_foregroundBlur_4380_34276" />
			</filter>
		</defs>
	</svg>

	<div
		style={Object.keys($tableState.streamingRows).length !== 0 ? 'opacity: 0%;' : ''}
		class="absolute top-0 left-0 h-full w-full z-[9] bg-[#BF416E] opacity-100 group-hover/gen-btn:opacity-0 group-hover/gen-btn:motion-reduce:opacity-100 group-hover/gen-btn:motion-reduce:bg-[#950048] group-focus/gen-btn:opacity-0 transition-opacity duration-300"
	></div>

	<div class="flex items-center gap-1.5 z-10">
		<div class="stars relative text-[#FCFCFD]">
			<StarIcon class="h-4 w-4 rotate-180 transition-[color,transform] duration-300" />
			<StarIcon
				class="stars absolute -bottom-1 -left-1 h-1.5 w-1.5 opacity-0 group-hover/gen-btn:opacity-100 group-focus/gen-btn:opacity-100 transition-opacity duration-300"
			/>
			<StarIcon
				class="stars absolute -top-1 -right-1 h-[7px] w-[7px] opacity-0 group-hover/gen-btn:opacity-100 group-focus/gen-btn:opacity-100 transition-opacity duration-300"
			/>
		</div>
		<span class="hidden sm:block"> Generate </span>
	</div>
</Button>

<style>
	:global(.group\/gen-btn:focus) .stars > :global(*:nth-child(1)),
	:global(.group\/gen-btn:hover) .stars > :global(*:nth-child(1)) {
		transform: rotate(0deg);
		animation: 3s ease-in-out 600ms infinite rotate-bottom-left;
	}

	.stars > :global(*:nth-child(2)) {
		animation: rotate-bottom-left 3s ease-in-out infinite;
	}

	.stars > :global(*:nth-child(3)) {
		animation: rotate-top-right 3s ease-in-out infinite;
	}

	@keyframes rotate-bottom-left {
		0% {
			transform: rotate(0deg);
		}
		35% {
			transform: rotate(90deg);
		}
		70% {
			transform: rotate(0deg);
		}
		100% {
		}
	}

	@keyframes rotate-top-right {
		0% {
			transform: rotate(0deg);
		}
		25% {
			transform: rotate(90deg);
		}
		50% {
			transform: rotate(180deg);
		}
		100% {
			transform: rotate(360deg);
		}
	}
</style>
