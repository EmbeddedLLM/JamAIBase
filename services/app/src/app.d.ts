/* eslint-disable @typescript-eslint/ban-types */
// See https://kit.svelte.dev/docs/types#app

import type { Auth0User, User } from '$lib/types';

// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		interface Locals {
			ossMode: boolean;
			auth0Mode: boolean;
			user?: Partial<Auth0User> & User;
		}
		// interface PageData {}
		interface PageState {
			page?: number;
		}
		// interface Platform {}
	}
}

export {};
