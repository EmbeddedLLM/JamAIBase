<script lang="ts">
	import Chart from 'chart.js/auto';
	import { type ChartItem } from 'chart.js';
	import { getDaysInMonth } from 'date-fns';
	import { cn } from '$lib/utils';
	import type { TUsageData } from '$lib/types';

	interface Props {
		usageData: TUsageData['data'];
		class?: string;
	}

	let { usageData, class: className = '' }: Props = $props();

	let chart: Chart;
	let ctx: HTMLCanvasElement | null;

	async function createChart(usageData: TUsageData['data']) {
		if (chart) chart.destroy();

		const baseColor = '#0AB9C4';
		const gradient = ctx!.getContext('2d')!.createLinearGradient(0, 0, 0, 450);
		gradient.addColorStop(0, baseColor + 'A0');
		gradient.addColorStop(1, baseColor + '10');

		chart = new Chart(ctx as ChartItem, {
			type: 'line',
			data: {
				labels: usageData.map((item) => item.date.split('T')[0]),
				datasets: [
					{
						label: 'Egress',
						data: usageData.map((item) => item.amount),
						backgroundColor: gradient,
						fill: true,
						borderWidth: 2,
						borderColor: baseColor,
						pointRadius: 5,
						tension: 0.2
					}
				]
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
								// @ts-ignore
								`${dataset.label}: ${raw?.toFixed(6)} GiB`
						}
					},
					legend: {
						display: false,
						labels: { color: '#475467' }
					}
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
						stacked: true,
						ticks: {
							count: 5,
							color: '#98A2B3'
						},
						beginAtZero: true,
						grid: { color: '#F2F4F7' }
					}
				}
			}
		});
	}

	$effect(() => {
		createChart(usageData);
	});
</script>

<div class={cn('h-[24rem] py-4 pb-2 sm:h-full sm:px-2', className)} style="position: relative;">
	<canvas bind:this={ctx}></canvas>
</div>
