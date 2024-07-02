<script lang="ts">
	import { PUBLIC_IS_LOCAL } from '$env/static/public';
	import { activeOrganization } from '$globalStore';
	import { cn } from '$lib/utils';

	let className: string | undefined | null = undefined;
	export { className as class };
</script>

<span class={cn('text-sm text-[#999999] capitalize', className)}>
	{PUBLIC_IS_LOCAL === 'false' ? $activeOrganization?.role ?? 'Unknown' : 'Admin'}
</span>
