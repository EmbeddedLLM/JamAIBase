<script lang="ts">
	import { onMount } from 'svelte';
	import * as monaco from 'monaco-editor';

	let { code = $bindable() }: { code: string } = $props();

	let editorContainer: any;
	let editor: ReturnType<typeof monaco.editor.create>;
	let insertAtCursor: ((text: string) => void) | undefined;

	export function insertText(text: string) {
		insertAtCursor?.(text);
	}

	onMount(() => {
		editor = monaco.editor.create(editorContainer, {
			value: code,
			language: 'python',
			theme: 'vs-dark',
			automaticLayout: true,
			fontSize: 14,
			minimap: { enabled: false },
			scrollBeyondLastLine: false
		});

		editor.onDidChangeModelContent(() => {
			code = editor.getValue();
		});

		insertAtCursor = function (text: string) {
			const position = editor.getPosition();
			if (!position) return;
			const range = new monaco.Range(
				position.lineNumber,
				position.column,
				position.lineNumber,
				position.column
			);
			editor.executeEdits('insert-text', [
				{
					range: range,
					text: text,
					forceMoveMarkers: true
				}
			]);
			// Move cursor to end of inserted text
			const newPosition = {
				lineNumber: position.lineNumber,
				column: position.column + text.length
			};
			editor.setPosition(newPosition);
			editor.focus();
		};

		return () => {
			editor.dispose();
		};
	});

	$effect(() => {
		if (editor && code) {
			const currentValue = editor.getValue();
			if (currentValue !== code) {
				editor.setValue(code);
			}
		}
	});
</script>

<div bind:this={editorContainer} style="height: 600px; border: 1px solid #ccc;"></div>
