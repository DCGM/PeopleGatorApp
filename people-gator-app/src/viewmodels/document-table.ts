import { ref, watch, type Ref } from 'vue'
import type { DocumentResponse, DocumentSortField } from '@/client'
import type { ColumnSizingState, ColumnVisibilityState } from '@tanstack/vue-table'

export const DOCUMENT_ANNOTATION_STATES = [
  { id: 'total', label: 'Total' },
  { id: 'automatic', label: 'Automatic' },
  { id: 'manual', label: 'Manual' },
  { id: 'verified', label: 'Verified' },
  { id: 'unassigned', label: 'Unassigned' },
] as const

export const DOCUMENT_ANNOTATION_GROUPS = [
  { id: 'all_annotations', label: 'All annotations', scope: 'all' },
  { id: 'faces', label: 'Faces', scope: 'faces' },
  { id: 'mentions', label: 'Text mentions', scope: 'mentions' },
] as const

type AnnotationScope = (typeof DOCUMENT_ANNOTATION_GROUPS)[number]['scope']
type AnnotationState = (typeof DOCUMENT_ANNOTATION_STATES)[number]['id']

export function annotationColumnId(scope: AnnotationScope, state: AnnotationState) {
  return scope === 'all' ? state : `${scope}_${state}`
}

export const DOCUMENT_COLUMN_IDS = [
  'first_page',
  'name',
  'ndk',
  'library',
  'registered_page_count',
  'linked_entity_count',
  ...DOCUMENT_ANNOTATION_GROUPS.flatMap((group) =>
    DOCUMENT_ANNOTATION_STATES.map((state) => annotationColumnId(group.scope, state.id)),
  ),
  'document_id',
  'last_modified',
  'modified_by',
  'api_key',
] as const
const DEFAULT_COLUMNS = new Set([
  'first_page',
  'name',
  'ndk',
  'library',
  'registered_page_count',
  'linked_entity_count',
  'total',
  'faces_total',
  'mentions_total',
])
export const DOCUMENT_COLUMNS_STORAGE_KEY = 'people-gator:document-columns'

export function defaultDocumentColumns(): ColumnVisibilityState {
  return Object.fromEntries(DOCUMENT_COLUMN_IDS.map((id) => [id, DEFAULT_COLUMNS.has(id)]))
}

export function readDocumentColumns(storage: Pick<Storage, 'getItem'>): ColumnVisibilityState {
  const fallback = defaultDocumentColumns()
  try {
    const saved: unknown = JSON.parse(storage.getItem(DOCUMENT_COLUMNS_STORAGE_KEY) ?? 'null')
    if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return fallback
    const valid = Object.entries(saved).filter(
      ([id, value]) =>
        DOCUMENT_COLUMN_IDS.includes(id as (typeof DOCUMENT_COLUMN_IDS)[number]) &&
        typeof value === 'boolean',
    )
    if (!valid.length) return fallback
    return { ...fallback, ...Object.fromEntries(valid) }
  } catch {
    return fallback
  }
}

export const DOCUMENT_COLUMN_ORDER_STORAGE_KEY = 'people-gator:document-column-order'

export function defaultDocumentColumnOrder(): string[] {
  return [...DOCUMENT_COLUMN_IDS]
}

/** Saved order with unknown IDs dropped and new fields appended in default order. */
export function readDocumentColumnOrder(storage: Pick<Storage, 'getItem'>): string[] {
  const fallback = defaultDocumentColumnOrder()
  try {
    const saved: unknown = JSON.parse(storage.getItem(DOCUMENT_COLUMN_ORDER_STORAGE_KEY) ?? 'null')
    if (!Array.isArray(saved)) return fallback
    const known = [...new Set(saved.filter((id) => fallback.includes(id)))]
    return [...known, ...fallback.filter((id) => !known.includes(id))]
  } catch {
    return fallback
  }
}

/** Places `id` before or after `target`; other columns keep their relative order. */
export function moveDocumentColumn(order: string[], id: string, target: string, after: boolean) {
  if (id === target) return order
  const next = order.filter((column) => column !== id)
  const index = next.indexOf(target)
  if (index < 0) return order
  next.splice(after ? index + 1 : index, 0, id)
  return next
}

/** Moves `id` one position among the visible columns. */
export function stepDocumentColumn(order: string[], visible: string[], id: string, step: -1 | 1) {
  const neighbour = visible[visible.indexOf(id) + step]
  return neighbour === undefined ? order : moveDocumentColumn(order, id, neighbour, step > 0)
}

/** Places a newly shown column after the last visible one. */
export function appendDocumentColumn(order: string[], visible: string[], id: string) {
  const others = visible.filter((column) => column !== id)
  const last = others[others.length - 1]
  return last === undefined
    ? [id, ...order.filter((column) => column !== id)]
    : moveDocumentColumn(order, id, last, true)
}

function usePersisted<T>(key: string, read: (storage: Storage) => T, fallback: () => T) {
  let initial = fallback()
  try {
    // Existing durable choices always win. Import the old tab preference only
    // when this browser has never saved the corresponding durable setting.
    initial = read(
      window.localStorage.getItem(key) === null ? window.sessionStorage : window.localStorage,
    )
  } catch {
    /* Storage can be disabled. */
  }
  const value = ref(initial) as Ref<T>
  watch(
    value,
    (next) => {
      try {
        window.localStorage.setItem(key, JSON.stringify(next))
      } catch {
        /* Keep in-memory choices usable. */
      }
    },
    { deep: true, immediate: true },
  )
  return value
}

export function useDocumentColumns() {
  return usePersisted(DOCUMENT_COLUMNS_STORAGE_KEY, readDocumentColumns, defaultDocumentColumns)
}

export function useDocumentColumnOrder() {
  return usePersisted(
    DOCUMENT_COLUMN_ORDER_STORAGE_KEY,
    readDocumentColumnOrder,
    defaultDocumentColumnOrder,
  )
}

export const DOCUMENT_COLUMN_SIZING_STORAGE_KEY = 'people-gator:document-column-sizing'

/** Sanitize persisted and interactive widths with the same column bounds. */
export function normalizeDocumentColumnSizing(saved: unknown): ColumnSizingState {
  if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return {}
  const widths: ColumnSizingState = {}
  for (const [id, value] of Object.entries(saved)) {
    if (
      (id !== 'identity' &&
        !DOCUMENT_COLUMN_IDS.includes(id as (typeof DOCUMENT_COLUMN_IDS)[number])) ||
      typeof value !== 'number' ||
      !Number.isFinite(value) ||
      value <= 0
    )
      continue
    const { minSize, maxSize } = documentColumnSizing(id)
    widths[id] = Math.min(maxSize, Math.max(minSize, value))
  }
  return widths
}

export function readDocumentColumnSizing(storage: Pick<Storage, 'getItem'>): ColumnSizingState {
  try {
    return normalizeDocumentColumnSizing(
      JSON.parse(storage.getItem(DOCUMENT_COLUMN_SIZING_STORAGE_KEY) ?? 'null'),
    )
  } catch {
    return {}
  }
}

export function useDocumentColumnSizing() {
  return usePersisted<ColumnSizingState>(
    DOCUMENT_COLUMN_SIZING_STORAGE_KEY,
    readDocumentColumnSizing,
    () => ({}),
  )
}

export function annotationCount(
  document: DocumentResponse,
  state: AnnotationState,
  scope: AnnotationScope = 'all',
) {
  if (!document.entity_link_stats) return null
  if (scope !== 'all') return document.entity_link_stats[scope]?.[state] ?? 0
  return (
    (document.entity_link_stats.faces?.[state] ?? 0) +
    (document.entity_link_stats.mentions?.[state] ?? 0)
  )
}

/** Only server-supported fields can offer header sorting. */
export const DOCUMENT_COLUMN_SORTS: Readonly<Partial<Record<string, DocumentSortField>>> = {
  name: 'name',
  library: 'library',
  document_id: 'document_id',
  registered_page_count: 'page_count',
  last_modified: 'last_touched_at',
  ...Object.fromEntries(
    DOCUMENT_ANNOTATION_GROUPS.flatMap((group) =>
      DOCUMENT_ANNOTATION_STATES.map((state) => [
        annotationColumnId(group.scope, state.id),
        `${group.scope === 'all' ? 'annotations' : group.scope}_${state.id}_count` as DocumentSortField,
      ]),
    ),
  ),
}

/** Preferred CSS-pixel widths at every viewport; overflow belongs to the table region. */
export function documentColumnSizing(id: string) {
  const widths: Record<string, number> = {
    identity: 280,
    name: 320,
    ndk: 80,
    first_page: 120,
    library: 200,
    document_id: 320,
    registered_page_count: 120,
    last_modified: 208,
    modified_by: 224,
    api_key: 224,
    linked_entity_count: 144,
  }
  // Count headers fit their title, menu chevron and sort strip on one line:
  // Annotations needs the most room, then Mentions; Faces keeps the 128px default.
  const annotation = DOCUMENT_ANNOTATION_STATES.some((s) => s.id === id)
  const size = widths[id] ?? (annotation ? 168 : id.startsWith('mentions_') ? 144 : 128)
  const minSize = id === 'name' || id === 'identity' || id === 'document_id' ? 200 : size
  const maxSize =
    id === 'name' || id === 'identity' || id === 'document_id' ? 720 : Math.max(size * 2, 240)
  return { size, minSize, maxSize }
}
