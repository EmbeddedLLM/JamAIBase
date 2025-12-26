<script lang="ts">
	import { PUBLIC_JAMAI_URL } from '$env/static/public';
	import axios from 'axios';
	import { Camera, Clipboard, Clock } from '@lucide/svelte';
	import { page } from '$app/state';
	import { activeProject } from '$globalStore';
	import { projectState } from '../../projectState.svelte.js';
	import converter from '$lib/showdown';
	import { fileColumnFiletypes, tagColors } from '$lib/constants';
	import logger from '$lib/logger';

	import {
		EditProjectInfoDialog,
		EditProjectReadmeDialog,
		ProjectThumbFetch
	} from './(components)';
	import { toast, CustomToastDesc } from '$lib/components/ui/sonner';
	import { Button } from '$lib/components/ui/button';
	import PermissionGuard from '$lib/components/PermissionGuard.svelte';
	import PeopleIcon from '$lib/icons/PeopleIcon.svelte';
	import LoadingSpinner from '$lib/icons/LoadingSpinner.svelte';
	import EditIcon from '$lib/icons/EditIcon.svelte';

	let { data } = $props();

	let imageUploadContainer = $state<HTMLDivElement | undefined>();
	let uploadController: AbortController | undefined;
	let projectImgThumb = $state('');

	let isEditingProjectProfile = $state(false);
	let isEditingProjectReadme = $state(false);

	function handleSelectFiles(files: File[]) {
		imageUploadContainer
			?.querySelectorAll('input[type="file"]')
			?.forEach((el) => ((el as HTMLInputElement).value = ''));

		if (files.length === 0) return;
		if (files.length > 1) {
			alert('Cannot upload multiple files in one column');
			return;
		}

		if (
			files.some(
				(file) =>
					!fileColumnFiletypes
						.filter(({ type }) => type === 'image')
						.map(({ ext }) => ext)
						.includes('.' + (file.name.split('.').pop() ?? '').toLowerCase())
			)
		) {
			alert(
				`Files must be of type: ${fileColumnFiletypes
					.filter(({ type }) => type === 'image')
					.map(({ ext }) => ext)
					.join(', ')
					.replaceAll('.', '')}`
			);
			return;
		}

		handleFilesUpload(files);
	}

	async function handleFilesUpload(files: File[]) {
		uploadController = new AbortController();

		const formData = new FormData();
		formData.append('file', files[0]);

		try {
			const uploadRes = await axios.post(`${PUBLIC_JAMAI_URL}/api/owl/files/upload`, formData, {
				headers: {
					'Content-Type': 'multipart/form-data',
					'x-project-id': page.params.project_id
				},
				signal: uploadController.signal
			});

			if (uploadRes.status !== 200) {
				logger.error('PROJECT_IMG_UPLOAD', {
					file: files[0].name,
					response: uploadRes.data
				});
				alert(
					'Failed to upload file: ' +
						(uploadRes.data.message || JSON.stringify(uploadRes.data)) +
						`\nRequest ID: ${uploadRes.data.request_id}`
				);
				return;
			} else {
				const updateProjectImgRes = await fetch(
					`${PUBLIC_JAMAI_URL}/api/owl/projects?${new URLSearchParams([['project_id', page.params.project_id ?? '']])}`,
					{
						method: 'PATCH',
						headers: {
							'Content-Type': 'application/json'
						},
						body: JSON.stringify({
							cover_picture_url: uploadRes.data.uri
						})
					}
				);

				if (!updateProjectImgRes.ok) {
					const updateProjectImgBody = await updateProjectImgRes.json();
					logger.error('PROJECT_IMG_UPDATE', updateProjectImgBody);
					toast.error('Failed to update project image', {
						id: updateProjectImgBody.message || JSON.stringify(updateProjectImgBody),
						description: CustomToastDesc as any,
						componentProps: {
							description: updateProjectImgBody.message || JSON.stringify(updateProjectImgBody),
							requestID: updateProjectImgBody.request_id
						}
					});
				} else {
					location.reload();
				}
			}
		} catch (err) {
			uploadController = undefined;

			if (!(err instanceof axios.CanceledError && err.code == 'ERR_CANCELED')) {
				//@ts-expect-error AxiosError
				logger.error('PROJECT_IMG_UPLOAD', err?.response?.data);
				alert(
					'Failed to upload file: ' +
						//@ts-expect-error AxiosError
						(err?.response?.data.message || JSON.stringify(err?.response?.data)) +
						//@ts-expect-error AxiosError
						`\nRequest ID: ${err?.response?.data?.request_id}`
				);
			}
		}
	}
</script>

<svelte:head>
	<title>Overview</title>
</svelte:head>

{#if $activeProject}
	<div class="grid h-full grid-cols-[minmax(300px,4fr)_minmax(0,10fr)]">
		<div class="flex h-full flex-col">
			<div class="flex h-1 grow flex-col overflow-auto px-6 py-3">
				<div class="relative h-32 w-full rounded-lg border p-[5px]">
					{#if projectImgThumb}
						<!-- Temp fix for url -->
						<img
							src={projectImgThumb.replace('http://', 'https://')}
							class="h-full w-full rounded-md object-cover"
							alt=""
						/>
					{:else if $activeProject && !$activeProject?.cover_picture_url}
						<div class="flex h-full items-center justify-center rounded-md bg-secondary">
							<Clipboard class="h-10 w-10 text-white" />
						</div>
					{:else}
						<div class="flex h-full items-center justify-center">
							<LoadingSpinner class="h-4 w-4 text-secondary" />
						</div>
					{/if}

					<PermissionGuard reqOrgRole="ADMIN" reqProjRole="ADMIN">
						<div
							bind:this={imageUploadContainer}
							class="absolute -bottom-5 -right-5 rounded-full bg-[#F2F4F7] p-1"
						>
							<Button
								onclick={(e) => {
									if (uploadController === undefined) {
										e.currentTarget.querySelector('input')?.click();
									}
								}}
								class="aspect-square h-8 w-8 rounded-full p-0"
							>
								<Camera class="h-5" />

								<input
									type="file"
									accept={fileColumnFiletypes
										.filter(({ type }) => type === 'image')
										.map(({ ext }) => ext)
										.join(',')}
									onchange={(e) => {
										e.preventDefault();
										handleSelectFiles([...(e.currentTarget.files ?? [])]);
									}}
									multiple={false}
									class="fixed max-h-[0] max-w-0 overflow-hidden !border-none !p-0"
								/>
							</Button>
						</div>
					</PermissionGuard>
				</div>

				<p class="mt-4 text-lg font-medium text-[#344054]">{$activeProject?.name}</p>

				{#if $activeProject?.description}
					<p class="mt-1 text-sm text-[#667085]">{$activeProject?.description}</p>
				{/if}

				{#if ($activeProject?.tags?.length ?? 0) > 0}
					<div class="mt-2 flex flex-wrap gap-1">
						{#each $activeProject?.tags ?? [] as tag, index}
							<span
								style="background-color: {tagColors[index % tagColors.length]};"
								class="select-none rounded-md px-1.5 py-[3px] text-xs text-white"
							>
								{tag}
							</span>
						{/each}
					</div>
				{/if}

				<PermissionGuard reqOrgRole="ADMIN" reqProjRole="ADMIN">
					<button
						onclick={() => (isEditingProjectProfile = true)}
						class="mt-4 w-full rounded-xl border bg-white p-2 text-sm transition-colors hover:bg-[#F9FAFB]"
					>
						Edit Project Info
					</button>
				</PermissionGuard>

				<div class="mt-3 flex flex-col gap-1">
					<div class="flex items-center gap-1 text-sm">
						<PeopleIcon class="mb-0.5 h-4 w-4 text-[#667085]" />
						<span class="font-medium text-[#344054]">
							{#await data.projectMembers}
								0
							{:then projectMembers}
								{projectMembers.data?.length}
							{/await}
						</span><span class="text-[#667085]">members</span>
					</div>

					{#if $activeProject?.created_at}
						<div class="flex items-center gap-[5px] text-sm">
							<Clipboard class="mb-px h-3.5 w-3.5 text-[#667085]" />
							<span class="text-[#667085]">Created at</span><span
								class="font-medium text-[#344054]"
							>
								{new Date($activeProject.created_at).toLocaleString(undefined, {
									day: 'numeric',
									month: 'short',
									year: 'numeric'
								})}
							</span>
						</div>
					{/if}

					{#if $activeProject?.updated_at}
						<div class="flex items-center gap-1 text-sm">
							<Clock class="h-3.5 w-3.5 text-[#667085]" />
							<span class="text-[#667085]">Last updated at</span><span
								class="font-medium text-[#344054]"
							>
								{new Date($activeProject.updated_at).toLocaleString(undefined, {
									day: 'numeric',
									month: 'short',
									year: 'numeric'
								})}
							</span>
						</div>
					{/if}
				</div>

				<PermissionGuard reqOrgRole="ADMIN" reqProjRole="ADMIN">
					<div class="mt-4 flex flex-col rounded-lg bg-[#F9FAFB] p-3">
						<span class="text-[#475467]">Project Deletion</span>

						<p class="mt-1 text-sm text-[#667085]">
							Permanently delete this project and all its data.
						</p>

						<Button
							variant="destructive"
							onclick={() => (projectState.isDeletingProject = page.params.project_id ?? null)}
							class="mt-4 h-[unset] w-max px-2 py-1 font-normal"
						>
							Delete Project
						</Button>
					</div>
				</PermissionGuard>
			</div>
		</div>

		<div class="relative my-3 mr-6 flex flex-col rounded-lg border border-[#E4E7EC]">
			{#if $activeProject?.meta?.readme}
				<div class="h-1 grow overflow-auto px-3 py-4">
					<p class="response-message flex flex-col gap-4 whitespace-pre-line text-sm">
						{@html converter.makeHtml(($activeProject.meta?.readme as string) ?? '')}
					</p>
				</div>
			{:else}
				<div class="h-1 grow overflow-auto px-3 py-4">
					<p class="text-sm italic text-muted-foreground">No description</p>
				</div>
			{/if}

			<PermissionGuard reqOrgRole="ADMIN" reqProjRole="ADMIN">
				<div class="absolute right-2 top-2 flex gap-2">
					<Button
						variant="action"
						onclick={() => (isEditingProjectReadme = true)}
						class="aspect-square h-7 w-7 rounded-lg p-0"
					>
						<EditIcon class="h-4 w-4 text-[#475467]" />
					</Button>
				</div>
			</PermissionGuard>
		</div>
	</div>

	<ProjectThumbFetch project={$activeProject} bind:projectImgThumb />
	<EditProjectInfoDialog bind:isEditingProjectProfile />
	<EditProjectReadmeDialog bind:isEditingProjectReadme />
{:else}
	<div class="flex h-full items-center justify-center">
		<LoadingSpinner class="h-6 w-6 text-secondary" />
	</div>
{/if}
