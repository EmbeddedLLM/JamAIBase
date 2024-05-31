/* eslint-disable @typescript-eslint/ban-types */
// See https://kit.svelte.dev/docs/types#app
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		interface Locals {
			user?: User;
		}
		interface PageData {
			user?: User;
		}
		// interface Platform {}
	}
}

type User = {
	sid: string;
	given_name?: string;
	nickname: string;
	name: string;
	picture: string;
	locale?: string;
	updated_at: '2024-05-06T17:16:18.952Z';
	email: string;
	email_verified: boolean;
	sub: string;
};

export {};
