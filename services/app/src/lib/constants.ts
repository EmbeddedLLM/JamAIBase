import {
	allenai,
	anthropic,
	cohere,
	deepseek,
	gemini,
	generic,
	generic2,
	meta,
	mistral,
	openai,
	qwen
} from '$lib/assets/model-icons';

export const emailCodeCooldownSecs = 600;

export const currencies = {
	USD: 'United States Dollar',
	EUR: 'Euro',
	GBP: 'British Pound Sterling',
	JPY: 'Japanese Yen',
	AUD: 'Australian Dollar',
	CAD: 'Canadian Dollar',
	CHF: 'Swiss Franc',
	CNY: 'Chinese Yuan',
	INR: 'Indian Rupee',
	NZD: 'New Zealand Dollar',
	SEK: 'Swedish Krona',
	SGD: 'Singapore Dollar',
	HKD: 'Hong Kong Dollar',
	KRW: 'South Korean Won',
	MXN: 'Mexican Peso'
} as Record<string, string>;

/** Map model type keys to display labels */
export const MODEL_TYPES = {
	completion: 'Completion',
	llm: 'LLM',
	embed: 'Embed',
	rerank: 'Rerank',
	image_gen: 'Image Gen'
} as Record<string, string>;

export const MODEL_CAPABILITIES = {
	completion: 'Completion',
	chat: 'Chat',
	tool: 'Tool',
	reasoning: 'Reasoning',
	image: 'Image',
	image_out: 'Image Out',
	audio: 'Audio',
	embed: 'Embed',
	rerank: 'Rerank'
} as Record<string, string>;

export const modelLogos = {
	openai: {
		src: openai,
		title: 'OpenAI Logo'
	},
	anthropic: {
		src: anthropic,
		title: 'Anthropic Logo'
	},
	cohere: {
		src: cohere,
		title: 'Cohere Logo'
	},
	deepseek: {
		src: deepseek,
		title: 'Deepset Logo'
	},
	mistral: {
		src: mistral,
		title: 'Mistral Logo'
	},
	qwen: {
		src: qwen,
		title: 'Qwen Logo'
	},
	google: {
		src: gemini,
		title: 'Gemini Logo'
	},
	meta: {
		src: meta,
		title: 'Meta Logo'
	},
	allenai: {
		src: allenai,
		title: 'AllenAI logo'
	},
	generic: {
		src: generic,
		title: 'Generic AI Model Logo'
	},
	generic2: {
		src: generic2,
		title: 'Generic AI Model Logo'
	}
};

export const PROVIDERS = {
	anthropic: 'Anthropic',
	azure: 'Azure',
	azure_ai: 'Azure AI',
	bedrock: 'Bedrock',
	cerebras: 'Cerebras',
	cohere: 'Cohere',
	deepseek: 'Deepseek',
	ellm: 'ELLM',
	gemini: 'Gemini',
	groq: 'Groq',
	hyperbolic: 'Hyperbolic',
	jina_ai: 'Jina AI',
	openai: 'OpenAI',
	openrouter: 'OpenRouter',
	sagemaker: 'SageMaker',
	sambanova: 'SambaNova',
	together_ai: 'Together AI',
	vertex_ai: 'Vertex AI',
	voyage: 'Voyage'
} as Record<string, string>;

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
export const tableIDPattern = /^[A-Za-z0-9]([A-Za-z0-9.?!@#$%^&*_()\- ]*[A-Za-z0-9.?!()\- ])?$/;
export const columnIDPattern = /^[A-Za-z0-9]([A-Za-z0-9.?!@#$%^&*_()\- ]*[A-Za-z0-9.?!()\- ])?$/;
export const promptVariablePattern = /\$\{([^}]*)\}/g;
export const pythonVariablePattern = /row\["([^"]+)"\]/g;
export const chatCitationPattern = /\[(@\d+(?:; @\d+)*)\]/g;

const LLM_GEN_CONFIG_DEFAULT = {
	object: 'gen_config.llm',
	model: '',
	system_prompt: '',
	prompt: '',
	temperature: 1,
	max_tokens: 1000,
	top_p: 0.1
} as const;
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const CODE_GEN_CONFIG_DEFAULT = {
	object: 'gen_config.code',
	source_column: ''
} as const;
const PYTHON_GEN_CONFIG_DEFAULT = {
	object: 'gen_config.python',
	python_code: ''
} as const;

export const genTableColTypes = {
	Input: null,
	'LLM Output': LLM_GEN_CONFIG_DEFAULT,
	// 'Code Output': CODE_GEN_CONFIG_DEFAULT,
	'Python Output': PYTHON_GEN_CONFIG_DEFAULT
} as const;
export const genTableDTypes = {
	int: 'Integer',
	float: 'Float',
	bool: 'Boolean',
	str: 'Text',
	image: 'Image',
	audio: 'Audio',
	document: 'Document'
} as Record<string, string>;
export const genTableColDTypes = {
	Input: Object.keys(genTableDTypes),
	'LLM Output': ['str', 'image'],
	// 'Code Output': ['str', 'image', 'audio'],
	'Python Output': ['str', 'image', 'audio']
} as Record<keyof typeof genTableColTypes, (keyof typeof genTableDTypes)[]>;

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
	{ ext: '.jpeg', type: 'image' },
	{ ext: '.jpg', type: 'image' },
	{ ext: '.png', type: 'image' },
	{ ext: '.gif', type: 'image' },
	{ ext: '.webp', type: 'image' },
	{ ext: '.wav', type: 'audio' },
	{ ext: '.mp3', type: 'audio' },
	{ ext: '.csv', type: 'document' },
	{ ext: '.tsv', type: 'document' },
	{ ext: '.txt', type: 'document' },
	{ ext: '.md', type: 'document' },
	{ ext: '.doc', type: 'document' },
	{ ext: '.docx', type: 'document' },
	{ ext: '.pdf', type: 'document' },
	{ ext: '.ppt', type: 'document' },
	{ ext: '.pptx', type: 'document' },
	{ ext: '.xls', type: 'document' },
	{ ext: '.xlsx', type: 'document' },
	{ ext: '.xml', type: 'document' },
	{ ext: '.html', type: 'document' },
	{ ext: '.json', type: 'document' },
	{ ext: '.jsonl', type: 'document' }
];

export const tagColors = [
	'#e74d73',
	'#4db2d6',
	'#4d69e8',
	'#e8b04d',
	'#9b4de8',
	'#e84d4d',
	'#4de8e1',
	'#6f4de8',
	'#e84db8'
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

export const ROLE_COLORS: Record<(typeof userRoles)[number], string> = {
	ADMIN: '#FAB21D',
	MEMBER: '#4DB4FE',
	GUEST: '#5478E4'
};

export const jamaiApiVersion = '0.5.0';

export const actionRowsPerPage = 100;
export const knowledgeRowsPerPage = 20;
export const chatRowsPerPage = 100;

export const reasoningEffortEnum = ['disabled', 'minimal', 'low', 'medium', 'high'];

//* Non-local
export const userRoles = ['GUEST', 'MEMBER', 'ADMIN'] as const;
