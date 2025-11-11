<script lang="ts">
	import { mount } from 'svelte';
	import Chart from 'chart.js/auto';
	import { type ChartItem } from 'chart.js';
	import { getDaysInMonth } from 'date-fns';
	import { cn } from '$lib/utils';
	import type { TUsageData } from '$lib/types';

	import Checkbox from '$lib/components/Checkbox.svelte';

	interface Props {
		usageData: TUsageData[];
		legendContainer: HTMLDivElement | undefined;
	}

	let { usageData, legendContainer }: Props = $props();

	const barColors = [
		'#BF416E',
		'#8CA4EC',
		'#FFB6C3',
		'#4169E1',
		'#B6F4F7',
		'#09324F',
		'#EE8698',
		'#D5607C',
		'#2DC6D1',
		'#019AA3',
		'#ED336B',
		'#0295FF'
	];

	let chart: Chart;
	let ctx: HTMLCanvasElement | null;

	const getOrCreateLegendList = (chart: any, container: HTMLDivElement) => {
		let listContainer = container.querySelector('ul');

		if (!listContainer) {
			listContainer = document.createElement('ul');
			listContainer.className =
				'flex flex-col overflow-x-hidden overflow-y-auto m-0 h-[26rem] sm:h-[32rem]';

			const tableHeader = document.createElement('div');
			tableHeader.className =
				'grid grid-cols-[minmax(0,9fr)_minmax(85px,3fr)_50px] gap-1 pl-4 pr-2 font-medium text-[#667085] text-xs sm:text-sm';
			const model = document.createElement('span');
			model.appendChild(document.createTextNode('Models'));
			tableHeader.appendChild(model);
			const tokens = document.createElement('span');
			tokens.appendChild(document.createTextNode('Tokens'));
			tableHeader.appendChild(tokens);
			container.className = cn('flex flex-col gap-2', container.className);
			container.appendChild(tableHeader);
			container.appendChild(listContainer);
		}

		return listContainer;
	};

	const htmlLegendPlugin = {
		id: 'htmlLegend',
		afterUpdate(chart: Chart, args: any, options: { container: HTMLDivElement }) {
			const ul = getOrCreateLegendList(chart, options.container);

			// Remove old legend items
			while (ul.firstChild) {
				ul.firstChild.remove();
			}

			// Reuse the built-in legendItems generator
			const items = chart.options.plugins!.legend!.labels!.generateLabels!(chart);

			if (items.length === 0 || (items.length === 1 && items[0].text === '')) {
				const span = document.createElement('span');
				span.className = 'self-center my-auto';
				span.appendChild(document.createTextNode('No data available'));
				ul.appendChild(span);
			} else {
				const itemsSorted: ((typeof items)[number] & { tokens: number })[] = items
					.map((item) => ({
						...item,
						tokens: chart.data.datasets[item.datasetIndex!].data.reduce(
							(acc: number, val) => (typeof val === 'number' ? acc + val : acc),
							0
						)
					}))
					.sort((a, b) => b.tokens - a.tokens);

				itemsSorted.forEach((item) => {
					const li = document.createElement('li');
					li.className =
						'grid grid-cols-[minmax(0,9fr)_minmax(85px,3fr)_50px] items-center gap-1 pl-4 pr-2 py-0.5';
					li.style.color = item.fontColor!.toString();

					const modelDiv = document.createElement('div');
					modelDiv.className = 'grid grid-cols-[20px_1fr] items-center gap-1';

					const tokensSpan = document.createElement('span');
					tokensSpan.className = 'pl-1 font-medium';
					tokensSpan.appendChild(document.createTextNode(item.tokens.toLocaleString()));

					// Color box
					const boxSpan = document.createElement('span');
					boxSpan.style.background = item.fillStyle!.toString();
					boxSpan.style.borderColor = item.strokeStyle!.toString();
					boxSpan.style.borderWidth = item.lineWidth + 'px';
					boxSpan.style.display = 'inline-block';
					boxSpan.style.flexShrink = '0';
					boxSpan.className = 'h-[18px] w-[18px] rounded-[2px]';

					// Text
					const textContainer = document.createElement('p');
					li.style.background = !item.hidden ? '#FFF7F8' : '';
					textContainer.style.wordBreak = 'break-word';
					textContainer.className = 'm-0 p-0';
					textContainer.appendChild(document.createTextNode(item.text));

					const checkboxContainer = document.createElement('div');
					checkboxContainer.className = 'flex items-center justify-center';

					mount(Checkbox, {
						target: checkboxContainer,
						props: {
							checked: !item.hidden,
							class: 'h-[18px] w-[18px] [&>svg]:h-3 [&>svg]:w-3 [&>svg]:translate-x-[2px]'
						},
						events: {
							checkedChange: () => {
								//@ts-expect-error
								const { type } = chart.config;
								if (type === 'pie' || type === 'doughnut') {
									// Pie and doughnut charts only have a single dataset and visibility is per item
									chart.toggleDataVisibility(item.index!);
								} else {
									chart.setDatasetVisibility(
										item.datasetIndex!,
										!chart.isDatasetVisible(item.datasetIndex!)
									);
								}
								chart.update();
							}
						}
					});

					modelDiv.appendChild(boxSpan);
					modelDiv.appendChild(textContainer);
					li.appendChild(modelDiv);
					li.appendChild(tokensSpan);
					li.appendChild(checkboxContainer);
					ul.appendChild(li);
				});
			}
		}
	};

	async function createChart(usageData: TUsageData[]) {
		if (chart) chart.destroy();
		chart = new Chart(ctx as ChartItem, {
			type: 'bar',
			data: {
				labels: usageData[0].data.map((row) => row.date.split('T')[0]),
				datasets: usageData
					.map<Chart['data']['datasets'][number] & { sum: number }>((item) => ({
						label: item.model,
						data: item.data.map((row) => row.amount),
						sum: item.data.reduce((acc, { amount }) => acc + amount, 0)
					}))
					.sort((a, b) => b.sum - a.sum)
					.map((item, index) => ({
						...item,
						backgroundColor: barColors[index % barColors.length]
					}))
			},
			options: {
				plugins: {
					subtitle: { display: false },
					colors: { enabled: true },
					tooltip: {
						callbacks: {
							title: (context) => {
								if (context?.length >= 1) {
									const dateTimeStrParts = context[0].label.split(',');
									dateTimeStrParts.pop();

									return dateTimeStrParts.join(',');
								}
							},
							label: ({ dataset, raw }) => `${dataset.label}: ${raw?.toLocaleString()} tokens`
						}
					},
					legend: {
						display: false,
						labels: { color: '#475467' }
					},
					//@ts-ignore
					htmlLegend: { container: legendContainer }
				},
				responsive: true,
				maintainAspectRatio: false,
				aspectRatio: 0.6,
				scales: {
					x: {
						grid: { display: false },
						border: { display: false },
						stacked: true,
						type: 'time',
						ticks: {
							callback: (val, index) => {
								return index % (getDaysInMonth(new Date(val)) === 30 ? 4 : 5) === 0
									? new Date(val).toLocaleString(undefined, { day: 'numeric', month: 'short' })
									: undefined;
							},
							color: '#98A2B3'
						},
						time: {
							unit: 'day',
							displayFormats: { day: 'D MMM' }
						}
					},
					y: {
						title: {
							display: true,
							text: 'MTok',
							color: '#98A2B3',
							padding: { top: 0, bottom: 0, y: 0 }
						},
						border: { display: false },
						stacked: true,
						ticks: {
							count: 5,
							callback: (val) => Number(val) / 1_000_000,
							stepSize: 500_000,
							color: '#98A2B3'
						},
						beginAtZero: true,
						grid: { color: '#F2F4F7' }
					}
				}
			},
			plugins: [htmlLegendPlugin]
		});
	}

	$effect(() => {
		createChart(usageData);
	});
</script>

<div class="h-[24rem] pb-0 pt-4 sm:h-auto sm:px-2" style="position: relative;">
	<canvas bind:this={ctx}></canvas>
</div>
