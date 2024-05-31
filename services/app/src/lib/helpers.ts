export function getFirstDayOfMonth(date: Date) {
	const firstDay = new Date(date.getFullYear(), date.getMonth(), 1);
	firstDay.setHours(0, 0, 0, 0); // Setting to the beginning of the day
	return firstDay;
}

export function getLastDayOfMonth(date: Date) {
	const lastDay = new Date(date.getFullYear(), date.getMonth() + 1, 0);
	lastDay.setHours(23, 59, 59, 999); // Setting to the last millisecond of the day
	return lastDay;
}

export function formatDateToDayMonthAbbr(date: Date) {
	const newDate = new Date(date);
	const day = newDate.getDate().toString().padStart(2, '0');
	const month = newDate.toLocaleDateString('en-US', { month: 'short' });
	return `${day} ${month}`;
}
