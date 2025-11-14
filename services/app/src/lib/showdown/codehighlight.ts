/* eslint-disable @typescript-eslint/no-explicit-any */
import showdown from 'showdown';
import hljs from 'highlight.js';
import '../../hljs-theme.css';

function htmlunencode(text: string) {
	return text.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
}
const codehighlight = [
	{
		type: 'output',
		filter: function (text: string) {
			const left = '<pre><code\\b[^>]*>',
				right = '</code></pre>',
				flags = 'g',
				replacement = function (wholeMatch: any, match: string, left: string, right: string) {
					match = htmlunencode(match);
					return left + hljs.highlightAuto(match).value + right;
				};
			return showdown.helper.replaceRecursiveRegExp(text, replacement, left, right, flags);
		}
	}
];
export default codehighlight;
