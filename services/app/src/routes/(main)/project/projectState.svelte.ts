export class ProjectState {
	isDeletingProject = $state<string | null>(null);
}

export const projectState = new ProjectState();
