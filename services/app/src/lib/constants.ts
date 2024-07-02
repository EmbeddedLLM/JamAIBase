export const timestampsDisplayName: { [key: string]: string } = {
	today: 'Today',
	yesterday: 'Yesterday',
	two_days: 'Two days ago',
	three_days: 'Three days ago',
	last_week: 'Last week',
	last_month: 'Last month',
	older: 'Older'
};
export const genTableDTypes = ['int', 'float', 'bool', 'str'] as const;
export const idPattern = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,98}[a-zA-Z0-9]$/;

//* Non-local
export const userRoles = ['guest', 'member', 'admin'] as const;
