export const timestampsDisplayName: { [key: string]: string } = {
	today: 'Today',
	yesterday: 'Yesterday',
	two_days: 'Two days ago',
	three_days: 'Three days ago',
	last_week: 'Last week',
	last_month: 'Last month',
	older: 'Older'
};
export const actionTableDTypes = ['int', 'float', 'bool', 'str'] as const;

//* Non-local
export const userRoles = ['guest', 'member', 'admin'] as const;
