<script lang="ts">
	import capitalize from 'lodash/capitalize';
	import Chart from 'chart.js/auto';
	import { type ChartItem } from 'chart.js';
	import { getDaysInMonth } from 'date-fns';
	import { cn } from '$lib/utils';
	import type { TUsageDataStorage } from '$lib/types';

	interface Props {
		usageData: TUsageDataStorage[];
		class?: string;
	}

	let { usageData, class: className = '' }: Props = $props();

	let chart: Chart;
	let ctx: HTMLCanvasElement | null;

	let storageLegendContainer: HTMLDivElement;

	const getOrCreateLegendList = (chart: any, container: HTMLDivElement) => {
		let listContainer = container.querySelector('ul');

		if (!listContainer) {
			container.className = 'absolute top-0 right-0';
			listContainer = document.createElement('ul');
			listContainer.className = 'flex gap-3 overflow-x-hidden overflow-y-auto m-0 p-0 pr-2';

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
				items.reverse().forEach((item) => {
					const li = document.createElement('li');
					li.className = 'grid grid-cols-[20px_1fr] place-items-center gap-0.5 cursor-pointer';
					li.style.color = item.fontColor!.toString();

					li.onclick = () => {
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
					};

					// Color box
					const boxSpan = document.createElement('span');
					boxSpan.style.background = item.strokeStyle!.toString();
					boxSpan.style.display = 'inline-block';
					boxSpan.style.flexShrink = '0';
					boxSpan.className = 'h-[15px] w-[15px] rounded-[3px]';

					// Text
					const textContainer = document.createElement('p');
					textContainer.style.textDecoration = item.hidden ? 'line-through' : '';
					textContainer.style.wordBreak = 'break-word';
					textContainer.className = 'm-0 p-0 text-sm';

					textContainer.appendChild(
						document.createTextNode(item.text === 'db' ? 'Database' : capitalize(item.text))
					);

					li.appendChild(boxSpan);
					li.appendChild(textContainer);
					ul.appendChild(li);
				});
			}
		}
	};

	async function createChart(usageData: TUsageDataStorage[]) {
		if (chart) chart.destroy();

		const getGradient = (baseColor: string) => {
			const gradient = ctx!.getContext('2d')!.createLinearGradient(0, 0, 0, 450);
			gradient.addColorStop(0, baseColor + 'A0');
			gradient.addColorStop(1, baseColor + '10');

			return gradient;
		};

		const averages = usageData
			.map((item) => ({
				type: item.type,
				average: item.data.reduce((acc, { amount }) => acc + amount, 0) / item.data.length
			}))
			.sort((a, b) => a.average - b.average);

		chart = new Chart(ctx as ChartItem, {
			type: 'line',
			data: {
				labels: usageData[0].data.map((row) => row.date.split('T')[0]),
				datasets: usageData.map((item) => {
					return {
						label: item.type,
						data: item.data.map((row) => row.amount),
						backgroundColor: item.type === 'db' ? getGradient('#FA6F99') : getGradient('#4DB4FE'),
						fill: true,
						borderWidth: 2,
						borderColor: item.type === 'db' ? '#FA6F99' : '#4DB4FE',
						pointRadius: 5,
						tension: 0.2,
						order: averages.findIndex((average) => average.type === item.type)
					};
				})
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
							label: ({ dataset, raw }) =>
								`${
									dataset.label === 'db' ? 'DB' : capitalize(dataset.label)
									// @ts-ignore
								}: ${raw?.toFixed(6)} GiB`
						}
					},
					legend: {
						display: false,
						labels: { color: '#475467' }
					},
					//@ts-ignore
					htmlLegend: { container: storageLegendContainer }
				},
				responsive: true,
				maintainAspectRatio: false,
				aspectRatio: 0.6,
				scales: {
					x: {
						grid: { display: false },
						border: { display: false },
						stacked: false,
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
							text: 'GiB',
							color: '#98A2B3',
							padding: { top: 0, bottom: 0, y: 0 }
						},
						border: { display: false },
						stacked: false,
						ticks: {
							count: 5,
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

<div class={cn('h-[24rem] py-4 pb-2 sm:h-full sm:px-2', className)} style="position: relative;">
	<div bind:this={storageLegendContainer}></div>

	<canvas bind:this={ctx}></canvas>
</div>
