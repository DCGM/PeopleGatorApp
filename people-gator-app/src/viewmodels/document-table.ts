import type { DocumentResponse } from '@/client'
import type { ColumnVisibilityState } from '@tanstack/vue-table'

export function defaultDocumentColumns(): ColumnVisibilityState {
  return { first_page: false, document_id: false, modified_by: false, api_key: false }
}

export function annotationCount(
  document: DocumentResponse,
  state: 'total' | 'automatic' | 'verified' | 'manual' | 'unassigned',
) {
  if (!document.entity_link_stats) return null
  return (
    (document.entity_link_stats.faces?.[state] ?? 0) +
    (document.entity_link_stats.mentions?.[state] ?? 0)
  )
}
