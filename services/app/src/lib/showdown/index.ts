import codeblock from '$lib/showdown/codeblock';
import codehighlight from '$lib/showdown/codehighlight';
import table from '$lib/showdown/table';
import showdown from 'showdown';
//@ts-expect-error - no types
import showdownHtmlEscape from 'showdown-htmlescape';
import './showdown-theme.css';

const converter = new showdown.Converter({
	tables: true,
	tasklists: true,
	disableForced4SpacesIndentedSublists: true,
	strikethrough: true,
	ghCompatibleHeaderId: true,
	extensions: [showdownHtmlEscape, codeblock, codehighlight, table]
});

const guideConverter = new showdown.Converter({
	tables: true,
	tasklists: true,
	disableForced4SpacesIndentedSublists: true,
	strikethrough: true,
	ghCompatibleHeaderId: true,
	extensions: [codeblock, codehighlight, table]
});

export default converter;
export { codeblock, codehighlight, guideConverter, table };
