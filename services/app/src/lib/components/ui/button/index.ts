import Root from './button.svelte';
import { tv, type VariantProps } from 'tailwind-variants';
import type { Button as ButtonPrimitive } from 'bits-ui';

const buttonVariants = tv({
	base: 'inline-flex items-center justify-center text-sm font-medium whitespace-nowrap ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-full disabled:pointer-events-none disabled:opacity-50',
	variants: {
		variant: {
			default:
				'text-[#FCFCFD] bg-[#BF416E] hover:bg-[#950048] focus-visible:bg-[#950048] active:bg-[#7A003B]',
			destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
			outline:
				'text-[#BF416E] bg-transparent hover:bg-[#BF416E]/[0.025] focus-visible:bg-[#BF416E]/[0.025] active:bg-[#BF416E]/5 border border-[#BF416E]',
			'outline-neutral':
				'text-text bg-transparent hover:bg-[#F9FAFB] data-dark:hover:bg-white/[0.1] active:bg-[#F2F4F7] data-dark:bg-[#0D0E11] data-dark:hover:bg-white/[0.1] border border-[#DDD] data-dark:border-[#42464E]',
			action: 'bg-[#F2F4F7] hover:bg-[#E4E7EC] text-black rounded-md',
			warning: 'bg-warning hover:bg-warning/80 text-black',
			ghost: 'hover:bg-[#F2F4F7] hover:text-accent-foreground',
			link: 'text-primary underline-offset-4 hover:underline'
		},
		size: {
			default: 'h-10 px-4 py-2',
			sm: 'h-9 rounded-md px-3',
			lg: 'h-11 rounded-md px-8',
			icon: 'h-10 w-10'
		}
	},
	defaultVariants: {
		variant: 'default',
		size: 'default'
	}
});

type Variant = VariantProps<typeof buttonVariants>['variant'];
type Size = VariantProps<typeof buttonVariants>['size'];

type Props = ButtonPrimitive.Props & {
	variant?: Variant;
	size?: Size;
};

type Events = ButtonPrimitive.Events;

export {
	Root,
	type Props,
	type Events,
	//
	Root as Button,
	type Props as ButtonProps,
	type Events as ButtonEvents,
	buttonVariants
};
