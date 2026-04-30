# Frontend Design Principles

This document describes the architectural patterns and conventions used in this codebase. Any agent implementing new frontend features should follow these principles to produce consistent, idiomatic code.

## 0. Core Principles

- Keep server state in TanStack Query, UI state in Pinia, and derived state in `computed()`.
- Prefer small, composable, one-way data flows over shared mutable state.
- Keep views thin: they orchestrate composition, data loading, and layout, but do not own business logic.
- Put side effects at the boundary: API calls in query/mutation composables, browser APIs in composables or stores, and presentation logic in components.
- Optimize for readability first. If a pattern is hard to explain in one sentence, it is probably too complex for a shared frontend primitive.

---

## 1. File & Folder Layout

```
src/
├── api/            – Axios client class, TypeScript models, barrel export
├── components/     – Reusable UI components (no routing, no page logic)
├── composables/    – Reusable stateful logic (non-query, non-store)
├── layouts/        – Shell/layout wrappers used by the router
├── queries/        – TanStack Vue Query composables, one file per resource
│   └── keys.ts     – Centralised query key factory (single source of truth)
│   └── sseEventHandlers.ts – SSE connection + cache invalidation
├── router/         – Vue Router config
├── stores/         – Pinia stores for UI-only state
├── utils/          – Pure utility functions
└── views/          – Page-level components (owned by routes)
```

Rules:
- **Views** are owned by routes and orchestrate data fetching + layout. They are thin shells.
- **Components** are reusable and dumb relative to routing concerns.
- **Queries** own all server-state: fetch, mutate, cache.
- **Stores** own only ephemeral UI state (selection, collapsed panels, etc.). Never store server data in a Pinia store.

When a feature grows beyond a single view, prefer feature-oriented colocation over widening shared folders. Keep domain-specific components, queries, and composables near the feature that uses them.

---

## 2. TypeScript Throughout

- All files use strict TypeScript. No `any`.
- Model types live in `src/api/models.ts` and are imported wherever needed — never re-declared inline.
- Props and emits are typed with generics, not runtime validators.
- Prefer explicit return types on exported functions and composables when the inference is not obvious.
- Use `satisfies` for constant maps, key factories, and request payloads when it improves type safety without widening values.

```ts
// Correct: generic typed defineProps / defineEmits
const props = defineProps<{
  sessionId: string
}>()

const emit = defineEmits<{
  activated: [sessionId: string]
  createNew: [options: MutateSessionRequest | undefined]
}>()
```

---

## 3. Vue Component Style

Every component uses `<script setup lang="ts">`. The Options API is never used.

**Order within `<script setup>`:**
1. Imports (Vue core, PrimeVue, project modules)
2. `defineProps` / `defineEmits`
3. Query / mutation composables
4. Local `ref` / `reactive` state
5. `computed` properties
6. Event handlers / methods
7. `watch` calls

- Keep templates mostly declarative. Move branching, normalization, and formatting into `computed()` or small helpers.
- Prefer one responsibility per component. Extract a child component when a section has its own local state, loading state, or repeated markup.
- Use `watch` only for synchronization and side effects; use `computed()` for derived values.

```vue
<script lang="ts" setup>
import { ref, computed, watch } from 'vue'
import Button from 'primevue/button'
import { useSessionQuery } from '@/queries/useSessions'
import type { MutateSessionRequest } from '@/api/models'

const props = defineProps<{ sessionId: string }>()

const { data: session } = useSessionQuery(props.sessionId)
const name = ref('')
const isEditable = computed(() => session.value?.state === 'draft')

watch(session, (value) => {
  if (value) name.value = value.name
}, { immediate: true })
</script>
```

---

## 4. The `v-model` Component Pattern

Components that wrap a value use the standard Vue 3 `v-model` contract:

```ts
const props = defineProps<{ modelValue: string[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
```

Never mutate `modelValue` directly. Always emit the full new value.

---

## 5. API Client

All HTTP calls go through the `ImageCompassCaptureAPI` class in `src/api/client.ts`. The singleton is exported as `api` from `src/api/index.ts`.

- Each logical resource group (sessions, images, devices, tags…) has its own block of methods.
- Methods accept typed request objects and return typed response objects.
- Query parameters are built explicitly with `URLSearchParams` — no implicit coercion.
- SSE connections are opened via dedicated methods that return `EventSource`.
- Request and response types should map to API contracts directly. Avoid ad-hoc component-level reshaping unless the presentation layer truly needs it.
- If an endpoint has pagination, filtering, or sorting, encode those options explicitly in typed request objects rather than passing loose objects around.

```ts
// Adding a new endpoint: add a method to the class, use typed models
async updateSession(id: string, data: MutateSessionRequest): Promise<SessionMetadata> {
  const response = await this.client.patch<SessionMetadata>(`/sessions/${id}/`, data)
  return response.data
}
```

Never import Axios directly in components or query composables. Only `api` is imported.

---

## 6. TanStack Query — Queries

One file per resource in `src/queries/`. Each file exports one composable per operation.

**Required patterns:**
- `queryKey` is always a `computed()` wrapping the key factory — this makes it reactive to prop changes automatically.
- Params are typed as `MaybeRefOrGetter<T>` and unwrapped with `toValue()`, so the composable works with plain values, refs, or getters.
- Always set a `staleTime`. No queries should rely on the zero default.
  - Frequently-changing data (session details): `staleTime: 1000 * 10`
  - Moderate (session lists): `staleTime: 1000 * 30`
  - Slow (tags, devices): `staleTime: 1000 * 60`
  - Immutable (uploaded images): `staleTime: Infinity`
- Conditional fetching uses `enabled: computed(() => !!toValue(id))`.
- Query composables should expose the minimum surface area needed by the view. Prefer returning typed query results and a small number of derived helpers instead of forwarding the entire API response shape blindly.

```ts
export function useSessionQuery(sessionId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => sessionKeys.detail(toValue(sessionId))),
    queryFn: () => api.getSession(toValue(sessionId)),
    staleTime: 1000 * 10,
    enabled: computed(() => !!toValue(sessionId)),
  })
}
```

---

## 7. TanStack Query — Mutations

Mutations live in the same file as their related queries.

**Cache invalidation strategy (in order of preference):**
1. `queryClient.setQueryData(key, result)` — use when the server returns the updated entity; avoids an extra network round-trip.
2. `queryClient.invalidateQueries({ queryKey: ... })` — use for list invalidation or when the entity isn't returned.

Keep optimistic updates small and reversible. If the UI can remain correct with a short refetch, prefer cache updates only after success.

```ts
export function useUpdateSessionMutation(sessionId: MaybeRefOrGetter<string>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: MutateSessionRequest) =>
      api.updateSession(toValue(sessionId), data),
    onSuccess: (updated) => {
      queryClient.setQueryData(sessionKeys.detail(updated.id), updated)
      queryClient.invalidateQueries({ queryKey: sessionKeys.lists() })
    },
  })
}
```

Never call `queryClient` directly inside a component. All cache manipulation belongs inside mutation `onSuccess`/`onError` callbacks in the query file.

---

## 8. Query Key Factory

All query keys are defined in `src/queries/keys.ts`. Never write raw key arrays in components or query files.

Structure: `[resource, variant, ...specifics]`

```ts
export const sessionKeys = {
  all:     () => ['sessions'] as const,
  lists:   () => [...sessionKeys.all(), 'list'] as const,
  list:    (filters?) => [...sessionKeys.lists(), { filters }] as const,
  details: () => [...sessionKeys.all(), 'detail'] as const,
  detail:  (id: string) => [...sessionKeys.all(), 'detail', id] as const,
}
```

Broad invalidation uses `lists()` or `all()`; targeted invalidation uses `detail(id)`. This hierarchy means invalidating `lists()` does not bust individual detail entries.

Keep key shapes stable. Do not embed non-deterministic values, raw reactive objects, or large payloads in keys.

---

## 9. Pinia Stores — UI State Only

Stores hold state that:
- Is not server-fetched (that belongs in TanStack Query)
- Needs to survive navigation (e.g. which camera is selected, which panels are collapsed)

Use Pinia's **composition API** (`defineStore` with a setup function). Never use the options API form.

Persistence to `localStorage` follows a consistent pattern: hydrate once at store creation, persist on every write.

Always guard browser APIs so the store remains safe in tests and any non-browser execution path.

```ts
export const useCameraSelectionStore = defineStore('cameraSelection', () => {
  const selectedCameraId = ref<string | null>(null)

  const hydrateSelectedCameraId = () => {
    if (typeof window === 'undefined') return
    selectedCameraId.value = window.localStorage.getItem('selectedCameraId')
  }

  const setSelectedCameraId = (cameraId: string | null) => {
    selectedCameraId.value = cameraId
    if (typeof window === 'undefined') return
    if (cameraId) window.localStorage.setItem('selectedCameraId', cameraId)
    else window.localStorage.removeItem('selectedCameraId')
  }

  hydrateSelectedCameraId()
  return { selectedCameraId, setSelectedCameraId }
})
```

---

## 10. Auto-Save Pattern

Form fields that auto-save to the server use this pattern consistently:

1. Local `ref`s mirror the server state.
2. A boolean `isSyncingFromServer` guards against watch triggers during server→local sync.
3. A `watch` on the server data (with `{ immediate: true }`) syncs in, sets the flag, clears it with `nextTick`.
4. A `watch` on the local refs debounces outbound saves, checks the guard, only sends a payload when values actually changed.

```ts
const isSyncingFromServer = ref(true)

watch(session, (value) => {
  if (!value) return
  isSyncingFromServer.value = true
  delay.value = value.delay ?? null
  nextTick(() => { isSyncingFromServer.value = false })
}, { immediate: true })

let saveTimeout: number | undefined
watch([delay], () => {
  if (isSyncingFromServer.value) return
  if (saveTimeout) window.clearTimeout(saveTimeout)
  saveTimeout = window.setTimeout(() => {
    updateSession({ delay: delay.value })
  }, 500)
})
```

Debounce delays: **500 ms** for numeric fields, **300 ms** for tag/text fields.

Auto-save forms should also surface an explicit save state so the user can tell whether changes are pending, saving, or failed.

---

## 11. Real-Time Updates via SSE

The app uses Server-Sent Events for live data. The pattern is:

- `useEventsBySource(scope)` opens an `EventSource` and attaches event listeners for a typed event scope.
- Components that need live updates call `useEventsBySource` and call `cleanup()` in `onUnmounted`.
- SSE connections are not opened in query composables — they are opened explicitly by the view or component that owns the live-update concern.
- Model event hierarchy as an ordered list of cache targets, from narrowest to broadest: for example `sessionId`, then search/filter scope, then collection, then global fallback.
- Map each event to the first cache target that can be updated safely. If the event payload contains the updated entity or row, prefer `queryClient.setQueryData(...)` or `queryClient.setQueriesData(...)` over invalidation.
- Use `invalidateQueries(...)` only when the payload is incomplete, the affected cache shape is ambiguous, or the event affects multiple resources that are cheaper to refetch.
- Keep event handlers small and deterministic: decode the event, identify the target cache key(s), and update or invalidate in one place.

```ts
// In a view component
const { cleanup } = useEventsBySource({ mode: 'sse-all' })
onUnmounted(() => cleanup())
```

New SSE event types: add them to the constant arrays in `sseEventHandlers.ts` and handle invalidation in `createSSEMessageHandler`.

Avoid using SSE to transport data that can be expressed cleanly through query refetches. Reserve SSE for true live updates, not general-purpose fetch replacement.

---

## 12. Styling

**Framework stack:** Tailwind CSS v4 + PrimeVue with the Aura preset.

**Tailwind** is used for layout, spacing, and responsive grid:
```html
<div class="grid grid-cols-1 gap-6 md:grid-cols-[repeat(auto-fill,minmax(500px,1fr))]">
```

**PrimeVue** components are used for all interactive UI: buttons, inputs, cards, overlays, selects. Do not re-implement components that PrimeVue provides.

**Scoped styles** are used for component-specific overrides. Use `:deep()` to target PrimeVue internals:
```css
<style scoped>
:deep(.p-galleria-content) {
  background-color: transparent;
}
</style>
```

**CSS variables** from the PrimeVue Aura theme (`var(--p-surface-950)`, `var(--p-green-500)`, etc.) are used for colors and semantic values — never hard-coded hex values.

Dark mode is handled by the Aura preset via `darkModeSelector: 'system'`. No manual dark-mode classes are needed.

Design guidance:
- Prefer semantic spacing, typography, and color tokens over ad-hoc per-component styling.
- Keep layout responsive by default. Assume narrow screens first, then scale up.
- Use empty states, skeletons, and subtle transitions to make state changes feel intentional.
- Prefer PrimeVue primitives for interaction, but do not let the default component look dictate the whole page. Compose them into a clear visual hierarchy.

---

## 13. Component Decomposition

Extract a sub-component when any of these are true:
- The template section exceeds ~40 lines with distinct logical areas
- A pattern of props + logic is reused in more than one place
- A UI element has its own internal state that doesn't need to be owned by the parent

Sub-components receive their data via props or `v-model` and communicate upward only via `emit`. They do not directly call mutations that belong to the parent's domain — instead they emit an intent and the parent acts.

The exception: a sub-component **may** call its own query/mutation composables when that data is fully encapsulated (e.g. `SessionTagsInput` fetches the global tag list internally because the parent has no use for that data).

As a rule of thumb, if a child needs to coordinate local state, validation, and asynchronous behavior, it probably deserves to own a composable or be split further.

---

## 14. Router & Views

Routes are nested under a `DefaultLayout` wrapper. Views are named and map one-to-one with routes.

```ts
{
  path: '/',
  component: DefaultLayout,
  children: [
    { path: 'sessions', name: 'sessions', component: SessionsView },
    { path: 'sessions/:id', name: 'session', component: SessionView },
  ],
}
```

Views receive route params via `useRoute()`. They do not accept props from a parent — they are the top of the composition tree for their page.

`router.beforeEach` is the only place `document.title` is set.

Route-driven views should handle loading, empty, and error states explicitly. Never leave a page visually blank while data is in flight.

## 15. Accessibility, Validation, and Tests

- Use semantic HTML first. Reach for ARIA only when native elements are insufficient.
- All interactive controls must remain keyboard accessible and visibly focusable.
- Forms should validate locally before submit when the validation rule is cheap and deterministic.
- Pure utilities belong in unit tests; query composables should be covered by request and invalidation tests when practical; page-level flows deserve at least one happy-path smoke test.
- If a change touches API contracts or cache behavior, verify the key factory and invalidation path together.
