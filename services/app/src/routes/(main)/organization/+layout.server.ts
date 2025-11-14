import { env } from '$env/dynamic/private';
import logger from '$lib/logger';
import { getPrices } from '$lib/server/nodeCache';
import { error } from '@sveltejs/kit';
import Stripe from 'stripe';

const stripe = new Stripe(env.OWL_STRIPE_API_KEY);

export async function load({ cookies, depends, locals, parent }) {
	depends('layout:settings');
	const data = await parent();
	const { user, organizationData } = data;

	const prices = await getPrices(locals.user?.id);

	if (!data.ossMode && !prices) {
		throw error(500, 'Failed to get prices');
	}

	if (data.ossMode || !env.OWL_STRIPE_API_KEY || !locals.user) {
		return {
			prices,
			billing_info: [
				{ data: null, status: 401 },
				{ data: null, status: 401 }
			],
			payment_methods: { data: null, status: 401 }
		};
	}

	if (!user || !organizationData || !organizationData.stripe_id) {
		return {
			prices,
			billing_info: [
				{ data: null, status: 401 },
				{ data: null, status: 401 }
			],
			payment_methods: { data: null, status: 401 }
		};
		// throw error(500, 'Failed to get organization data');
	}

	//? check if user is in organization
	const activeOrganizationId = cookies.get('activeOrganizationId');
	if (!user.org_memberships.find((org) => org.organization_id === activeOrganizationId)) {
		throw error(403, 'Unauthorized');
	}

	const getSubscription = async () => {
		try {
			const subscription = await stripe.subscriptions.list({
				customer: organizationData.stripe_id!,
				expand: ['data.latest_invoice.payment_intent.latest_charge']
			});

			if (subscription.data.length > 0) {
				return { data: subscription.data[0], status: 200 };
			} else {
				return { data: null, status: 404, error: 'No subscription found' };
			}
		} catch (err) {
			if ((err as any).type === 'StripeInvalidRequestError' && (err as any).statusCode === 404) {
				return { data: null, status: 404, error: 'No subscription found' };
			} else {
				logger.error('SETTINGS_SUBSCRIPTION_GET', err);
				return { data: null, status: 500, error: err };
			}
		}
	};

	const getInvoice: () => Promise<{
		data: Stripe.Response<Stripe.UpcomingInvoice> | null;
		status: number;
		error?: any;
	}> = async () => {
		try {
			const invoice = await stripe.invoices.retrieveUpcoming({
				customer: organizationData.stripe_id!
			});
			return { data: invoice, status: 200 };
		} catch (err) {
			if ((err as any).type === 'StripeInvalidRequestError' && (err as any).statusCode === 404) {
				return { data: null, status: 404, error: 'No invoice found' };
			} else {
				logger.error('SETTINGS_INVOICE_GET', err);
				return { data: null, status: 500, error: err };
			}
		}
	};

	const getBillingInfo = () => {
		return [getSubscription(), getInvoice()] as const;
	};

	const getPaymentMethods = async (): Promise<{
		data: Stripe.PaymentMethod[] | null;
		status: number;
		error?: any;
	}> => {
		//? Get payment methods for customer
		try {
			const paymentMethods = await stripe.customers.listPaymentMethods(organizationData.stripe_id!);
			return { data: paymentMethods.data, status: 200 };
		} catch (err) {
			logger.error('SETTINGS_PAYMENTMETHODS_GET', err);
			return { data: null, status: 500, error: err };
		}
	};

	const getCustomer = async (): Promise<{
		data: Stripe.Customer | null;
		status: number;
		error?: any;
	}> => {
		try {
			const customer = await stripe.customers.retrieve(organizationData.stripe_id!);
			if (customer.deleted) {
				return { data: null, status: 404, error: 'Customer not found' };
			}
			return { data: customer, status: 200 };
		} catch (err) {
			logger.error('SETTINGS_CUSTOMER_GET', err);
			return { data: null, status: 500, error: err };
		}
	};

	const isAdmin =
		locals.user.org_memberships.find((org) => org.organization_id === activeOrganizationId)
			?.role === 'ADMIN';
	return {
		prices,
		billing_info: isAdmin
			? getBillingInfo()
			: [
					{ data: null, status: 403 },
					{ data: null, status: 403 }
				],
		payment_methods: isAdmin ? getPaymentMethods() : { data: null, status: 403 },
		customer: isAdmin ? await getCustomer() : { data: null, status: 403 }
	};
}
