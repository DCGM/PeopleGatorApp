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

export function defaultDocumentColumns(): ColumnVisibilityState {
  return {
    first_page: false,
    document_id: false,
    modified_by: false,
    api_key: false,
    ...Object.fromEntries(
      DOCUMENT_ANNOTATION_GROUPS.filter((group) => group.scope !== 'all').flatMap((group) =>
        DOCUMENT_ANNOTATION_STATES.map((state) => [
          annotationColumnId(group.scope, state.id),
          false,
        ]),
      ),
    ),
  }
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
}
