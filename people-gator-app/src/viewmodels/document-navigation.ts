import type { LocationQuery, LocationQueryRaw, RouteLocationRaw } from 'vue-router'
import type { DocumentResponse, PageResponse } from '@/client'
import { fetchDocuments, fetchPages } from '@/query/media'
import { GALLERY_VIEW_KEY } from '@/viewmodels/gallery-view'

/** Forward only the context supported by document-page browsing, never scan filters. */
export function documentBrowseQuery(query: LocationQuery): LocationQueryRaw {
  const keys = ['selectedPerson', 'gallery_person_only', 'gallery_sort', 'gallery_dir']
  return {
    ...Object.fromEntries(
      keys.flatMap((key) => (typeof query[key] === 'string' ? [[key, query[key]]] : [])),
    ),
    [GALLERY_VIEW_KEY]: 'expanded',
  }
}

function single(value: LocationQuery[string] | undefined): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined
}

/** Old Scans URLs are entry links only; cross-document scan search is retired. */
export function legacyScanLocation(query: LocationQuery): RouteLocationRaw {
  const document = single(query.document)
  const archive = single(query.archive_document)
  const library = single(query.library)
  const page = single(query.page)
  if (archive && library && !query.document)
    return {
      name: 'document-pages',
      params: { libraryId: library, documentId: archive },
      query: documentBrowseQuery(query),
    }
  if (document && !query.archive_document)
    return {
      name: 'document-source',
      params: { documentSourceId: document },
      query: { ...documentBrowseQuery(query), ...(library && { library }) },
    }
  if (page && !query.document && !query.archive_document) {
    const { pages_view: _expanded, ...context } = documentBrowseQuery(query)
    return { name: 'page-source', params: { pageSourceId: page }, query: context }
  }
  return { name: 'document-list', query: {}, hash: '' }
}

export type DocumentEntry = { sourceId: string } | { library: string; documentId: string }
export type DocumentEntryResult = {
  document?: DocumentResponse
  page?: PageResponse
}

/** Resolve one document, including archive IDs in old library-scoped links. */
export async function resolveDocumentEntry(
  entry: DocumentEntry,
  legacyLibrary?: string,
  signal?: AbortSignal,
): Promise<DocumentEntryResult> {
  let document: DocumentResponse | undefined
  let library: string | undefined
  let archive: string | undefined
  if ('sourceId' in entry) {
    const result = await fetchDocuments({ 'filter.source_id': [entry.sourceId], limit: 1 }, signal)
    document = result.items.find((item) => item.source_id === entry.sourceId)
    if (document && legacyLibrary && document.library !== legacyLibrary) return {}
    if (document) {
      library = document.library
      archive = document.document_id
    } else if (legacyLibrary) {
      library = legacyLibrary
      archive = entry.sourceId
    }
  } else {
    library = entry.library
    archive = entry.documentId
  }
  if (!library || !archive) return {}
  if (!document) {
    const result = await fetchDocuments(
      {
        'filter.library': [library],
        'filter.document_id': [archive],
        limit: 1,
      },
      signal,
    )
    document = result.items.find((item) => item.library === library && item.document_id === archive)
  }
  const result = await fetchPages(
    {
      'filter.library': [library],
      'filter.document_id': [archive],
      sort: 'page_number',
      sort_direction: 'asc',
      limit: 1,
    },
    signal,
  )
  const page = result.items.find((item) => item.library === library && item.document_id === archive)
  return { document, page }
}
