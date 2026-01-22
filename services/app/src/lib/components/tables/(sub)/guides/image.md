##### Basic Concept

The **Image Output Column** generates a single image per row using an image-generation model. You provide a prompt (which can reference upstream columns), and the model writes an image URI into the cell.

Create this column via **LLM Output** with **Data type = Image**.

The Image Output Column will:

1. Build a prompt from your text and any referenced columns.
2. Send the prompt to the selected image model.
3. Store the generated image in the cell as an image value.

You control:

- Prompt: The text instructions sent to the image model.
- Model: The image-capable model used for generation.

---

##### Referencing Upstream Columns in Prompts

You can reference upstream column values using:

> <span class="column-variable input-col">Column Name</span>

At runtime, each <span class="column-variable input-col">Column Name</span> is replaced with the current row's value.

For example:

> A cinematic portrait of <span class="column-variable input-col">Subject</span> in a neon city

To insert a reference, click the column chips above the prompt editor, or type `${Column Name}` directly.

---

##### Prompting Tips

- Be explicit about subject, style, lighting, and composition.
- If you need consistency, reuse the same phrasing across rows.
- Keep prompts concise and structured (e.g., "subject, style, scene, lighting").
