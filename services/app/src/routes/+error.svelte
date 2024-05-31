<script>
	import { page } from '$app/stores';
</script>

<svelte:head>
	<title>{$page.error.message}</title>
</svelte:head>

<main
	class="flex items-center justify-center m-0 h-screen text-black data-dark:text-white bg-white data-dark:bg-[#222]"
>
	<div class="flex items-center mx-4 my-0 max-w-[32rem]">
		<span class="relative -top-[0.05rem] text-5xl font-extralight">{$page.status}</span>
		<div
			class="flex items-center ml-4 pl-4 min-h-10 border-l border-[#ccc] data-dark:border-[#666]"
		>
			<h1>{$page.error.message}</h1>
		</div>
	</div>
</main>
