import { json } from '@sveltejs/kit';
import { z } from 'zod';
import { enumerateObj } from '$lib/utils.js';

export const POST = async ({ request, locals }) => {
	const body = await request.json().catch(() => null);

	let parsedBody;
	try {
		parsedBody = z
			.object({
				type: z.enum(['error', 'warn', 'info', 'log']),
				event: z.string(),
				message: z.any()
			})
			.parse(body);
	} catch (err) {
		return json({ message: 'Invalid body', err_message: err }, { status: 400 });
	}
	const { type, event, message } = parsedBody;

	const stringMessage =
		JSON.stringify(message) == '{}'
			? JSON.stringify(enumerateObj(message))
			: JSON.stringify(message);

	switch (type) {
		case 'error':
			console.error(
				`Logged from client (${locals.user?.sub ?? 'Unknown'}): ${event}\n`,
				stringMessage
			);
			break;
		case 'warn':
			console.warn(
				`Logged from client (${locals.user?.sub ?? 'Unknown'}): ${event}\n`,
				stringMessage
			);
			break;
		case 'info':
			console.info(
				`Logged from client (${locals.user?.sub ?? 'Unknown'}): ${event}\n`,
				stringMessage
			);
			break;
		case 'log':
			console.log(
				`Logged from client (${locals.user?.sub ?? 'Unknown'}): ${event}\n`,
				stringMessage
			);
			break;
		default:
			console.log(
				`Logged from client (${locals.user?.sub ?? 'Unknown'}): ${event}\n`,
				stringMessage
			);
			break;
	}

	return json({ message: 'Successfully logged' });
};
