import { ref, watch } from 'vue'
import type { DocumentResponse, DocumentSortField } from '@/client'
import type { ColumnVisibilityState } from '@tanstack/vue-table'

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
  'library',
  'registered_page_count',
  'linked_entity_count',
  ...DOCUMENT_ANNOTATION_GROUPS.flatMap((group) =>
    DOCUMENT_ANNOTATION_STATES.map((state) => annotationColumnId(group.scope, state.id)),
  ),
  'ndk',
  'document_id',
  'last_modified',
  'modified_by',
  'api_key',
] as const
const DEFAULT_COLUMNS = new Set([
  'first_page',
  'name',
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

export function useDocumentColumns() {
  let initial = defaultDocumentColumns()
  try {
    initial = readDocumentColumns(window.sessionStorage)
  } catch {
    /* Storage can be disabled. */
  }
  const visibility = ref(initial)
  watch(
    visibility,
    (value) => {
      try {
        window.sessionStorage.setItem(DOCUMENT_COLUMNS_STORAGE_KEY, JSON.stringify(value))
      } catch {
        /* Keep in-memory choices usable. */
      }
    },
    { deep: true },
  )
  return visibility
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
    registered_page_count: 104,
    total: 144,
    last_modified: 208,
    modified_by: 224,
    api_key: 224,
    linked_entity_count: 144,
  }
  const size = widths[id] ?? 128 // Count labels can wrap without changing the width model.
  const minSize = id === 'name' || id === 'identity' || id === 'document_id' ? 200 : size
  const maxSize =
    id === 'name' || id === 'identity' || id === 'document_id' ? 720 : Math.max(size * 2, 240)
  return { size, minSize, maxSize }
}
