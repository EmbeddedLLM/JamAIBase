<script lang="ts" module>
	import type { WithElementRef } from 'bits-ui';
	import type { HTMLAnchorAttributes, HTMLButtonAttributes } from 'svelte/elements';
	import { type VariantProps, tv } from 'tailwind-variants';
	export const buttonVariants = tv({
		base: 'inline-flex items-center justify-center text-sm font-medium whitespace-nowrap ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-xl disabled:pointer-events-none disabled:opacity-50',
		variants: {
			variant: {
				default:
					'text-[#FCFCFD] bg-[#BF416E] hover:bg-[#950048] focus-visible:bg-[#950048] active:bg-[#7A003B]',
				destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
				'destructive-init':
					'text-[#F04438] bg-white hover:bg-[#FEF3F2] border border-[#E4E7EC] !px-2 !py-1.5 rounded-lg font-normal',
				outline:
					'text-[#BF416E] bg-transparent hover:bg-[#BF416E]/[0.025] focus-visible:bg-[#BF416E]/[0.025] active:bg-[#BF416E]/5 border border-[#BF416E]',
				'outline-neutral':
					'text-[#475467] bg-transparent hover:bg-[#F2F4F7] data-dark:hover:bg-white/[0.1] active:bg-[#F2F4F7] data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1] border border-[#F2F4F7] data-dark:border-[#42464E] rounded-lg font-normal',
				action: 'bg-[#E4E7EC] hover:bg-[#D0D5DD] text-[#475467] rounded-lg',
				warning: 'bg-warning hover:bg-warning/80 text-black',
				ghost: 'hover:bg-[#E4E7EC] hover:text-accent-foreground',
				link: 'text-primary underline-offset-4 hover:underline'
			},
			size: {
				default: 'h-10 px-4 py-2',
				sm: 'h-8 px-3',
				lg: 'h-11 px-8',
				icon: 'h-10 w-10'
			},
			tvTheme: {
				true: ''
			}
		},
		compoundVariants: [
			{
				variant: 'default',
				tvTheme: true,
				class:
					'text-[#FCFCFD] bg-[#1B748A] hover:bg-[#145B6D] focus-visible:bg-[#145B6D] active:bg-[#145B6D]'
			},
			{
				variant: 'outline',
				tvTheme: true,
				class:
					'text-[#1B748A] bg-transparent hover:bg-[#1B748A]/[0.025] focus-visible:bg-[#1B748A]/[0.025] active:bg-[#1B748A]/5 border border-[#1B748A]'
			}
		],
		defaultVariants: {
			variant: 'default',
			size: 'default',
			tvTheme: false
		}
	});
	export type ButtonVariant = VariantProps<typeof buttonVariants>['variant'];
	export type ButtonSize = VariantProps<typeof buttonVariants>['size'];
	export type ButtonProps = WithElementRef<HTMLButtonAttributes> &
		WithElementRef<HTMLAnchorAttributes> & {
			variant?: ButtonVariant;
			size?: ButtonSize;
		} & {
			loading?: boolean;
			tvTheme?: boolean;
		};
</script>

<script lang="ts">
	import { cn } from '$lib/utils.js';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	let {
		class: className,
		variant = 'default',
		size = 'default',
		ref = $bindable(null),
		href = undefined,
		type = 'button',
		loading = false,
		tvTheme = false,
		children,
		...restProps
	}: ButtonProps = $props();
</script>

{#if href}
	<a
		bind:this={ref}
		class={cn(buttonVariants({ variant, size, tvTheme }), className)}
		{href}
		{...restProps}
	>
		{@render children?.()}
	</a>
{:else}
	<button
		bind:this={ref}
		class={cn(buttonVariants({ variant, size, tvTheme }), className)}
		{type}
		{...restProps}
	>
		{#if loading}
			<LoadingSpinner class="data-dark:text-white" />
		{/if}
		{@render children?.()}
	</button>
{/if}
