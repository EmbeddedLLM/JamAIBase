<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { activeOrganization } from '$globalStore';
	import { cn } from '$lib/utils';

	const { PUBLIC_IS_LOCAL } = env;

	let className: string | undefined | null = undefined;
	export { className as class };
</script>

<span class={cn('text-sm text-[#999999] capitalize', className)}>
	{PUBLIC_IS_LOCAL === 'false' ? $activeOrganization?.role ?? 'Unknown' : 'Admin'}
</span>
