export const timestampsDisplayName: { [key: string]: string } = {
	today: 'Today',
	yesterday: 'Yesterday',
	two_days: 'Two days ago',
	three_days: 'Three days ago',
	last_week: 'Last week',
	last_month: 'Last month',
	older: 'Older'
};
export const projectIDPattern = /^[a-zA-Z0-9][a-zA-Z0-9_ \-.]{0,98}[a-zA-Z0-9]$/;
export const tableIDPattern = /^[A-Za-z0-9]([A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$/;
export const columnIDPattern = /^[A-Za-z0-9]([A-Za-z0-9 _-]{0,98}[A-Za-z0-9])?$/;
export const genTableDTypes = {
	int: 'Integer',
	float: 'Float',
	bool: 'Boolean',
	str: 'Text',
	file: 'File',
	audio: 'Audio'
	// str_code: 'Text (code)',
	// file_code: 'File (code)'
} as Record<string, string>;
export const tableStaticCols = {
	action: ['ID', 'Updated at'] as string[],
	knowledge: [
		'ID',
		'Updated at',
		'Title',
		'Title Embed',
		'Text',
		'Text Embed',
		'File ID',
		'Page'
	] as string[],
	chat: ['ID', 'Updated at', 'User'] as string[]
} as const;
export const knowledgeTableEmbedCols = ['Title Embed', 'Text Embed'];
export const knowledgeTableFiletypes = [
	'.csv',
	'.tsv',
	'.txt',
	'.md',
	'.doc',
	'.docx',
	'.pdf',
	'.ppt',
	'.pptx',
	'.xls',
	'.xlsx',
	'.xml',
	'.html',
	'.json',
	'.jsonl'
];
export const fileColumnFiletypes = [
	{ ext: '.jpeg', type: 'file' },
	{ ext: '.jpg', type: 'file' },
	{ ext: '.png', type: 'file' },
	{ ext: '.gif', type: 'file' },
	{ ext: '.webp', type: 'file' },
	{ ext: '.wav', type: 'audio' },
	{ ext: '.mp3', type: 'audio' }
];
export const agentColors: { bg: string; text: string }[] = [
	{
		bg: '#FFD9E4',
		text: '#ED336B'
	},
	{
		bg: '#E3F2FD',
		text: '#0295FF'
	},
	{
		bg: '#D1F7F9',
		text: '#0AB9C4'
	},
	{
		bg: '#FFEAD5',
		text: '#F79009'
	}
];

export const jamaiApiVersion = '0.3.0';

export const actionRowsPerPage = 100;
export const knowledgeRowsPerPage = 20;
export const chatRowsPerPage = 100;

//* Non-local
export const userRoles = ['guest', 'member', 'admin'] as const;
