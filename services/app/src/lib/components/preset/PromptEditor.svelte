<script lang="ts">
	import 'prosemirror-view/style/prosemirror.css';
	import { onMount } from 'svelte';
	import { EditorState, Plugin } from 'prosemirror-state';
	import { EditorView } from 'prosemirror-view';
	import { Schema, DOMParser, Slice, Fragment, Node } from 'prosemirror-model';
	import { undo, redo, history } from 'prosemirror-history';
	import { keymap } from 'prosemirror-keymap';
	import { splitBlock, joinBackward, joinForward, deleteSelection } from 'prosemirror-commands';
	import type { GenTableCol } from '$lib/types';

	let {
		editorContent = $bindable(),
		usableColumns
	}: { editorContent: string; usableColumns: GenTableCol[] } = $props();

	let editorElement = $state<HTMLDivElement>();
	let editorView = $state<EditorView>();
	// let editorContent = $state('');

	const customSchema = new Schema({
		nodes: {
			doc: { content: 'block+' },
			paragraph: {
				content: 'inline*',
				group: 'block',
				parseDOM: [{ tag: 'p' }],
				toDOM() {
					return ['p', 0];
				}
			},
			text: { group: 'inline' },
			column_variable: {
				group: 'inline',
				inline: true,
				attrs: { text: {} },
				parseDOM: [
					{
						tag: 'span.column-variable',
						getAttrs(dom) {
							return { text: dom.textContent };
						}
					}
				],
				toDOM(node) {
					const column = usableColumns.find((col) => col.id === node.attrs.text);
					return [
						'span',
						{ class: `column-variable ${column?.gen_config ? 'output-col' : 'input-col'}` },
						node.attrs.text
					];
				}
			}
		}
	});

	const placeholderPlugin = new Plugin({
		appendTransaction(transactions, oldState, newState) {
			const tr = newState.tr;
			let modified = false;

			newState.doc.descendants((node, pos) => {
				if (node.isText) {
					const text = node.text || '';
					const regex = /\${([^}]+)}/g;
					let match;
					while ((match = regex.exec(text)) !== null) {
						const matchStart = pos + match.index;
						const matchEnd = matchStart + match[0].length;
						const content = match[1];
						const column = usableColumns.find((col) => col.id === content);

						if (!column) continue;

						tr.replaceWith(
							matchStart,
							matchEnd,
							customSchema.nodes.column_variable.create({ text: content })
						);
						modified = true;
					}
				}
			});

			return modified ? tr : null;
		}
	});

	// Custom clipboard text serializer
	const clipboardTextSerializer = (slice: Slice | Fragment) => {
		let text = '';
		slice.content.forEach((node, index) => {
			if (index !== 0 && node.type.name === 'paragraph') {
				text += '\n';
			}

			if (node.type.name === 'column_variable') {
				text += `\${${node.attrs.text}}`;
			} else if (node.isText) {
				text += node.text;
			} else {
				text += node.content.size ? clipboardTextSerializer(node.content) : '';
			}
		});
		return text;
	};

	const editorKeymap = keymap({
		'Mod-z': undo,
		'Mod-y': redo,
		'Mod-Shift-z': redo,
		Enter: splitBlock,
		Backspace: (state, dispatch, view) => {
			if (!state.selection.empty) return deleteSelection(state, dispatch, view);
			return joinBackward(state, dispatch, view);
		},
		Delete: (state, dispatch, view) => {
			if (!state.selection.empty) return deleteSelection(state, dispatch, view);
			return joinForward(state, dispatch, view);
		}
	});

	function parseEditorContent(content: string) {
		const dom = document.createElement('div');
		const paragraphs = content.split('\n');
		paragraphs.forEach((p) => {
			const pElement = document.createElement('p');
			let currentText = '';
			let match;
			const regex = /\${([^}]+)}/g;
			let lastIndex = 0;

			while ((match = regex.exec(p)) !== null) {
				if (match.index > lastIndex) {
					currentText += p.slice(lastIndex, match.index);
					pElement.appendChild(document.createTextNode(currentText));
					currentText = '';
				}

				const span = document.createElement('span');
				span.className = 'column-variable';
				span.textContent = match[1];
				pElement.appendChild(span);
				lastIndex = match.index + match[0].length;
			}

			if (lastIndex < p.length) {
				currentText += p.slice(lastIndex);
				pElement.appendChild(document.createTextNode(currentText));
			}
			// if (pElement.childNodes.length === 0 && p.length === 0) {
			// 	pElement.appendChild(document.createElement('br'));
			// }
			dom.appendChild(pElement);
		});

		return DOMParser.fromSchema(customSchema).parse(dom, { preserveWhitespace: 'full' });
	}

	function serializeEditorContent(doc: Node) {
		let text = '';
		doc.descendants((node, index) => {
			if (index !== 0 && node.type.name === 'paragraph') {
				text += '\n';
			}

			if (node.type.name === 'column_variable') {
				text += `\${${node.attrs.text}}`;
			} else if (node.isText) {
				text += node.text;
			}
		});
		return text;
	}

	onMount(() => {
		const state = EditorState.create({
			doc: parseEditorContent(editorContent),
			plugins: [
				history(),
				editorKeymap,
				placeholderPlugin,
				new Plugin({
					props: {
						clipboardTextSerializer
					}
				})
			]
		});

		editorView = new EditorView(editorElement!, {
			state,
			dispatchTransaction(transaction) {
				const newState = editorView!.state.apply(transaction);
				editorView!.updateState(newState);
				editorContent = serializeEditorContent(newState.doc);
			}
		});

		return () => {
			editorView?.destroy();
		};
	});

	export function insertTextAtCursor(text: string) {
		if (!editorView) return;

		const { state, dispatch } = editorView;
		const { selection } = state;
		const tr = state.tr.insertText(text, selection.from);

		dispatch(tr);
		editorView.focus();
		editorContent = serializeEditorContent(editorView.state.doc);
	}
</script>

<div bind:this={editorElement} class="prosemirror-editor"></div>

<style>
	.prosemirror-editor {
		flex-grow: 1;
		background-color: #f9fafb;
		border-radius: 6px;
		padding: 8px;
		border: 1px transparent solid;
		transition: border-color 150ms cubic-bezier(0.4, 0, 0.2, 1);
		overflow: auto;
		min-height: 350px;
	}

	.prosemirror-editor:focus-within {
		border-color: #d5607c;
		box-shadow: 0 0 0 1px #ffd8df;
	}

	:global(.ProseMirror) {
		min-height: 100%;
		font-size: 14px;
		outline: none !important;
	}

	:global(.column-variable) {
		padding: 2px 6px;
		border-radius: 8px;
		border: 1px solid #e4e7ec;
		font-size: 12px;
		display: inline-block;
	}

	:global(.output-col) {
		color: #fd853a;
	}

	:global(.input-col) {
		color: #7995e9;
	}
</style>
