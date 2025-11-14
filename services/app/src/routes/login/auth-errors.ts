export const AUTH_ERROR_MESSAGES = {
	invalid_credentials: 'Invalid email or password',
	default: 'An error occurred during authentication',
	user_exists: 'An account with this email already exists',
	user_not_found: 'No user found with the email provided',
	weak_password: 'Password should be at least 8 characters long',
	email_verification: 'Please verify your email address',
	account_disabled: 'Your account has been disabled',
	rate_limit: 'Too many attempts. Please try again later',
	invalid_token: 'Your session has expired. Please sign in again',
	server_error: 'Server error. Please try again later'
};

// Type to ensure the code is one of the keys in AUTH_ERROR_MESSAGES
export type TCode = keyof typeof AUTH_ERROR_MESSAGES;

export const getAuthErrorMessage = (code?: string | null): string => {
	if (code && code in AUTH_ERROR_MESSAGES) {
		return AUTH_ERROR_MESSAGES[code as TCode];
	}
	return AUTH_ERROR_MESSAGES.default;
};
