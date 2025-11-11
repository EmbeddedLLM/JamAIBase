import type { TUsageData } from '$lib/types';

export function fillMissingDaysForUsage(
	usageData: TUsageData['data'],
	firstDayOfMonth: string
): TUsageData['data'] {
	const sampleDate = new Date(firstDayOfMonth);
	const year = sampleDate.getFullYear();
	const month = sampleDate.getMonth();
	const daysInMonth = new Date(year, month + 1, 0).getDate();

	// Create a template for all days in the month
	const allDaysTemplate: {
		date: string;
		amount: number;
	}[] = [];
	for (let day = 1; day <= daysInMonth; day++) {
		const dateString = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}T00:00:00Z`;
		allDaysTemplate.push({ date: dateString, amount: 0 });
	}

	// Fill in the data for days that exist
	usageData.forEach((dayEntry) => {
		const day = new Date(dayEntry.date).getDate() - 1; // Adjust index to match template
		if (allDaysTemplate[day]) {
			allDaysTemplate[day].amount = dayEntry.amount;
		}
	});

	// Update the original data object with the complete set of days
	usageData = allDaysTemplate;

	return usageData;
}
