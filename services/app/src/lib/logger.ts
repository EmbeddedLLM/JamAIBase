/* eslint-disable @typescript-eslint/no-explicit-any */
import { browser } from '$app/environment';

export default class logger {
	public static async log(event: string, message: any, username?: string): Promise<void> {
		try {
			if (browser) {
				await fetch('/api/log', {
					method: 'POST',
					credentials: 'same-origin',
					body: JSON.stringify({ type: 'log', event, message })
				});
			} else {
				console.log(`Logged from server (${username ?? 'Unknown'}): ${event}\n`, message);
			}
		} catch (err) {
			console.error('Failed to log message', err);
		}
	}

	public static async error(event: string, message: any, username?: string): Promise<void> {
		try {
			if (browser) {
				await fetch('/api/log', {
					method: 'POST',
					credentials: 'same-origin',
					body: JSON.stringify({ type: 'error', event, message })
				});
				console.error(event, message);
			} else {
				console.error(`Logged from server (${username ?? 'Unknown'}): ${event}\n`, message);
			}
		} catch (err) {
			console.error('Failed to log error', err);
		}
	}
}

export class APIError {
	public readonly error: string;
	public readonly err_message: { message: string; [key: string]: any };

	constructor(error: string, err_message?: { message: string; [key: string]: any }) {
		this.error = error;
		this.err_message = err_message ?? { message: error };
	}
}
