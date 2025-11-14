const table = [
	{
		type: 'output',
		regex: '<table>',
		replace: function () {
			return '<div class="table-container"><table>'
		}
	},
	{
		type: 'output',
		regex: '</table>',
		replace: function () {
			return '</table></div>'
		}
	}
]

export default table
