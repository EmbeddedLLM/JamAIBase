# Frontend Design Spec — Image Output Column + Token Usage Tabs

## Summary

Add first-class **Image Output** gen-table columns and surface **token usage/quotas** (LLM/Image/Embed/Rerank) in the UI.
This spec aligns with:
- `plan/image_output_col_feature.md` (image output columns)
- `plan/image_gen_metrics.md` (image token usage + billing)

Backend is already implemented. This spec is frontend-only.

---

## Backend Verification Notes (Reviewed)

- `gen_config.image` is a strict, explicit discriminated config:
  - `object = "gen_config.image"` is required.
  - Defaults: `model = ""`, `prompt = ""`.
  - `size/quality/style` exist in backend but are **not** exposed in UI.
- Model type for image generation is `image_gen`.
- Image-capable models advertise `capabilities: ["image_out", ...]`.
- `/api/v2/meters/usages` supports `type=llm|image|embedding|reranking` and `groupBy=model`.
- Organizations expose:
  - `image_tokens_quota_mtok`
  - `image_tokens_usage_mtok`
  - `quotas.image_tokens` entry in the quota map.
- Price plans use product key `image_tokens`. Backend backfill labels unit as `"Million Tokens"`.
  - Frontend may continue using `"M Tokens"` for display consistency.

---

## Goals

1. Allow users to create and edit **Image Output** columns:
   - `dtype="image"`
   - `gen_config.object="gen_config.image"`
   - single image URI output per cell
2. Provide a clean settings UI for image output columns:
   - Prompt tab (templated prompt)
   - Model selection in the header row (no extra tab)
3. Show **image token quotas** in Organization Usage.
4. Show **token usage** in Analytics under a single chart with tabs (LLM/Image/Embed/Rerank).

---

## Non-goals

- No RAG, no system prompt, no multi-turn for image outputs.
- No image input/output token breakdown chart (text/image input/output) in analytics.
- No size/quality/style controls in UI (even though backend supports them).
- No backend changes.

---

## Data Contracts (Frontend Types)

### 1) `ImageGenConfig`

Add to `services/app/src/lib/types.ts`:

```ts
export interface ImageGenConfig {
  object: 'gen_config.image';
  model?: string;  // empty string means auto-select on backend
  prompt?: string;
  // size/quality/style are supported by backend but NOT exposed in UI for now
}
```

### 2) `GenTableCol.gen_config` union

Extend:
```ts
gen_config: (CodeGenConfig | LLMGenConfig | PythonGenConfig | EmbedGenConfig | ImageGenConfig) | null;
```

### 3) `ModelConfig.type`

Extend `services/app/src/lib/types.ts`:
```ts
type: 'completion' | 'llm' | 'embed' | 'rerank' | 'image_gen';
```

### 4) Model costs for image-gen

Extend `ModelConfig` with fields:
```ts
image_input_cost_per_mtoken: number;
image_output_cost_per_mtoken: number;
```

### 5) Organization quotas

Extend `OrganizationReadRes` with:
```ts
image_tokens_quota_mtok: number | null;
image_tokens_usage_mtok: number;
```

### 6) Price plan products

Extend `PriceRes.products` with:
```ts
image_tokens: PriceProduct;
```

---

## Constants and Labels

### 1) Model types

In `services/app/src/lib/constants.ts`:
```ts
export const MODEL_TYPES = {
  completion: 'Completion',
  llm: 'LLM',
  embed: 'Embed',
  rerank: 'Rerank',
  image_gen: 'Image Gen'
};
```

### 2) Model capabilities

Add `image_out` to `MODEL_CAPABILITIES` and use it to filter output-capable models:
```ts
export const MODEL_CAPABILITIES = [
  'completion', 'chat', 'tool', 'reasoning', 'image', 'image_out',
  'audio', 'embed', 'rerank'
] as const;
```

### 3) Gen table column types

In `services/app/src/lib/constants.ts`:

```ts
export const genTableColTypes = {
  Input: null,
  'LLM Output': LLM_GEN_CONFIG_DEFAULT,
  'Python Output': PYTHON_GEN_CONFIG_DEFAULT
} as const;

export const genTableColDTypes = {
  Input: Object.keys(genTableDTypes),
  'LLM Output': ['str', 'image'],
  'Python Output': ['str', 'image', 'audio']
};
```

**Note:** Image output is exposed as **LLM Output + dtype Image** in the UI for clarity. The frontend still sends `gen_config.image` when dtype is `image`.

---

## UI / UX Changes

### A) Add Column Dialog (LLM Output + Image dtype)

File: `services/app/src/routes/(main)/project/[project_id]/(dialogs)/AddColumnDialog.svelte`

**Behavior:**

1) When `isAddingColumn.type === 'output'`, allow **LLM Output** with `dtype=str|image`.

2) Selection rule:
   - If `selectedDatatype === 'image'` for output: treat as **Image Output** (send `gen_config.image`).
   - If `selectedDatatype === 'str'` for output: treat as **LLM Output** (send `gen_config.llm`).

3) Payload construction:

**LLM Output (unchanged):**
```json
{
  "object": "gen_config.llm",
  "model": "<selected>",
  "system_prompt": "<value>",
  "prompt": "<value>",
  "temperature": ...,
  "max_tokens": ...,
  "top_p": ...,
  "multi_turn": ...
}
```

**Image Output (new, via LLM Output + Image dtype):**
```json
{
  "object": "gen_config.image",
  "model": "<selected or ''>",
  "prompt": "<value>"
}
```

4) UI elements to show/hide:

| Output Mode | Show model select | Prompt editor | System prompt | temp/max/top_p | multi-turn |
|------------|-------------------|---------------|---------------|----------------|-----------|
| LLM (dtype=str) | Yes (cap=chat)    | Yes           | Yes           | Yes            | Yes       |
| LLM (dtype=image) | Yes (cap=image_out)| Yes        | No            | No             | No        |

5) Model select filter for image output:
```
capabilityFilter="image_out"
```

---

### B) Quick Add Column (PlaceholderNewCol)

File: `services/app/src/lib/components/tables/(sub)/PlaceholderNewCol.svelte`

**Behavior:**

- Keep **LLM Output** as the single AI output type.
- When `colType = 'LLM Output'` and `dType = 'image'`, send:
  - `gen_config = { object: 'gen_config.image', model: '', prompt: '' }`

---

### C) Column Settings (image output config)

File: `services/app/src/lib/components/tables/(sub)/ColumnSettings.svelte`

**Add `gen_config.image` support:**

- **Prompt tab** — use existing `PromptEditor`
- **Model selection** — place in the header row (same area as LLM model select)
  - `capabilityFilter="image_out"`
  - `bind:selectedModel={selectedGenConfig.model}`

**No system prompt, no RAG, no tools, no multi-turn.**

---

### D) Column Type Tag

File: `services/app/src/lib/components/tables/(sub)/ColumnTypeTag.svelte`

Show **LLM** label for image output columns (to match UI), while dtype remains `image`.

---

### E) How-To-Use Tab (optional but recommended)

File: `services/app/src/lib/components/tables/(sub)/HowToUseTab.svelte`

- Add a short guide `guides/image.md` (new file).
- Show it for `gen_config.image`.

If omitted, leave `how_to_use` tab hidden for image outputs.

---

## Analytics — Token Usage (Tabbed)

**Goal:** keep a single Token Usage card with tabs: LLM, Image, Embed, Rerank.

### 1) Server data fetch

File: `services/app/src/routes/(main)/analytics/+page.server.ts`

Add fetches (same schema):
```
GET /api/v2/meters/usages
  type=llm|image|embedding|reranking
  from, to, orgIds, windowSize=1d, groupBy=model
```
Reuse `tokenUsageSchema` because the payload shape matches (groupBy.model).

### 2) Page layout

File: `services/app/src/routes/(main)/analytics/+page.svelte`

Replace the single chart with a **tabbed card**:
- Tabs: LLM, Image, Embed, Rerank
- Reuse `TokenUsageChart` + single legend container
- Switching tabs swaps dataset only (no extra cards)

### 3) Chart behavior

Reuse existing `TokenUsageChart` exactly:
- datasets grouped by `model`
- labels based on day
- legend list showing model + total tokens

---

## Org Usage (Quotas)

File: `services/app/src/routes/(main)/organization/usage/+page.svelte`

No UI change is required if:
- `organizationData.quotas.image_tokens` exists
- `organizationData.price_plan.products.image_tokens` exists

The quotas grid already iterates over `organizationData.quotas` and renders any product it finds.

---

## Price Plan Admin (Cloud)

File: `services/app/src/routes/(main)/system/(cloud)/prices/+page.server.ts`

Add `image_tokens` to `priceSchema.products`:
```
image_tokens: productSchema('Image tokens', 'M Tokens')
```

Edit dialog should render the new product in the existing mapping.

---

## Model Admin UIs

### Add Model Config
File: `services/app/src/routes/(main)/system/models/(components)/AddModelConfigDialog.svelte`

Add `image_gen` to Model Type select.
When `modelType === image_gen`, show cost inputs:
- `llm_input_cost_per_mtoken`
- `llm_output_cost_per_mtoken`
- `image_input_cost_per_mtoken`
- `image_output_cost_per_mtoken`

### Model Details (Edit)
File: `services/app/src/routes/(main)/system/models/[model_id]/(components)/ModelDetails.svelte`

Support `image_gen` in type dropdown and show image cost fields in edit mode.

---

## Model Selection (Image Output)

File: `services/app/src/lib/components/preset/ModelSelect.svelte`

Extend prop type:
```
capabilityFilter?: 'completion' | 'chat' | 'image_out' | 'embed' | 'rerank';
```

Filter logic should match this new capability.

---

## Validation and Defaults (Frontend)

- `gen_config.image` defaults:
  - `model = ''` (backend resolves default)
  - `prompt = ''`
- No frontend validation for image/audio reference rules (backend rejects invalid prompt).
- No UI for `size/quality/style` in this phase.

---

## Acceptance Criteria

1) **Create image output column**
   - Add column dialog allows `LLM Output + dtype=image`.
   - Request payload includes `gen_config.image`.
2) **Edit image output column**
   - Column settings show Prompt tab.
   - Model selection appears in header row and filters by `image_out`.
3) **Render output**
   - Image cells display thumbnails (existing `FileColumnView` works).
   - Image cells surface generation errors when no image is produced.
4) **Analytics**
   - Analytics page shows a single Token Usage card with tabs (LLM/Image/Embed/Rerank).
   - Each tab is sourced from `/v2/meters/usages?type=<...>&groupBy=model`.
5) **Org usage**
   - Image tokens quota card appears when product/quotas are present.
6) **Admin**
   - Admin can create/edit image-gen models with proper cost fields.
   - Price plan editor includes `image_tokens`.

---

## Out of Scope / Future Extensions

- Size/quality/style controls in UI.
- Analytics breakdown by `type` (text_input/text_output/image_input/image_output).
- Per-provider UI variations for image generation.

---

## Implementation Plan + Worklog

### Phase 1 — Types & Constants
- [x] Add `ImageGenConfig` to `services/app/src/lib/types.ts`.
- [x] Extend `GenTableCol['gen_config']` union to include `ImageGenConfig`.
- [x] Extend `ModelConfig.type` with `image_gen`.
- [x] Add `image_input_cost_per_mtoken` + `image_output_cost_per_mtoken` to `ModelConfig`.
- [x] Extend `OrganizationReadRes` with `image_tokens_quota_mtok` + `image_tokens_usage_mtok`.
- [x] Extend `PriceRes.products` with `image_tokens`.
- [x] Update `MODEL_TYPES` and `MODEL_CAPABILITIES` in `services/app/src/lib/constants.ts`.
- [x] Allow `LLM Output` to support `dtype=image` in `genTableColDTypes`.

### Phase 2 — Column Creation + Editing
- [x] `AddColumnDialog.svelte`: support image output payload + UI changes.
- [x] `PlaceholderNewCol.svelte`: map `LLM Output + dtype=image` to `gen_config.image`.
- [x] `ColumnSettings.svelte`: add `gen_config.image` prompt + header model select.
- [x] `ColumnTypeTag.svelte`: show label `LLM` for `gen_config.image`.
- [x] Optional: `HowToUseTab.svelte` + `guides/image.md`.

### Phase 3 — Model Select & Admin
- [x] `ModelSelect.svelte`: extend `capabilityFilter` to include `image_out`.
- [x] `AddModelConfigDialog.svelte`: support `image_gen` + cost fields.
- [x] `ModelDetails.svelte`: support `image_gen` edit/view + cost fields.
- [x] `prices/+page.server.ts`: add `image_tokens` product to schema.

### Phase 4 — Analytics & Org Usage
- [x] `analytics/+page.server.ts`: add fetches for llm/image/embedding/reranking usage.
- [x] `analytics/+page.svelte`: add Token Usage tabs (LLM/Image/Embed/Rerank).
- [ ] Org usage UI should auto-render once `quotas.image_tokens` + product exist.

### Verification Checklist
- [ ] Create image output column via Add Column dialog.
- [ ] Create image output column via Quick Add (LLM Output + dtype=image).
- [ ] Edit image output column: Prompt tab + header model select (model filtered by `image_out`).
- [ ] Image cells render thumbnails (existing `FileColumnView`).
- [ ] Image cells show error messages on failed image generation.
- [ ] Analytics shows Token Usage tabs (LLM/Image/Embed/Rerank).
- [ ] Org usage shows Image Tokens quota card when present.
- [ ] Admin: create/edit `image_gen` model with image costs.
- [ ] Admin: price plan editor includes `image_tokens`.
