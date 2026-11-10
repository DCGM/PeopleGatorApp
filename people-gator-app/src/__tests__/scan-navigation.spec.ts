import type { LocationQuery } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { legacyScanLocation, resolveDocumentEntry } from '@/viewmodels/document-navigation'
const media = vi.hoisted(() => ({ fetchDocuments: vi.fn(), fetchPages: vi.fn() }))
vi.mock('@/query/media', () => media)
beforeEach(() => {
  vi.resetAllMocks()
  media.fetchDocuments.mockResolvedValue({ items: [] })
  media.fetchPages.mockResolvedValue({ items: [] })
})
describe('retired Scans entry links', () => {
  it('retains one document and supported gallery context, dropping global search filters', () => {
    expect(legacyScanLocation({ document: 'source', selectedPerson: 'ada', gallery_person_only: '1', q: 'name', link_state: 'manual' })).toEqual({
      name: 'document-source', params: { documentSourceId: 'source' },
      query: { selectedPerson: 'ada', gallery_person_only: '1', pages_view: 'expanded' },
    })
    expect(legacyScanLocation({ library: 'lib', archive_document: 'archive' })).toEqual({
      name: 'document-pages', params: { libraryId: 'lib', documentId: 'archive' }, query: { pages_view: 'expanded' },
    })
    expect(legacyScanLocation({ page: 'page-source', q: 'old' })).toEqual({ name: 'page-source', params: { pageSourceId: 'page-source' }, query: {} })
  })
  it.each<LocationQuery>([{}, { q: 'Ada' }, { library: 'lib' }, { document: ['a', 'b'] }, { archive_document: 'ambiguous' }])('returns Documents for global or ambiguous criteria %j', query => {
    expect(legacyScanLocation(query)).toEqual({ name: 'document-list', query: {}, hash: '' })
  })
})
describe('document entry resolution', () => {
  const document = { source_id: 'source', library: 'lib', document_id: 'archive', name: 'Ledger' }
  const page = { source_id: 'page-source', library: 'lib', document_id: 'archive', page_id: 'page' }
  it('resolves a source UUID then queries only its library/document first page', async () => {
    media.fetchDocuments.mockResolvedValue({ items: [document] })
    media.fetchPages.mockResolvedValue({ items: [page] })
    expect(await resolveDocumentEntry({ sourceId: 'source' })).toEqual({ document, page })
    expect(media.fetchDocuments).toHaveBeenCalledTimes(1)
    expect(media.fetchPages.mock.calls[0]![0]).toEqual({ 'filter.library': ['lib'], 'filter.document_id': ['archive'], sort: 'page_number', sort_direction: 'asc', limit: 1 })
  })
  it('retains a registered empty document without inventing a page', async () => {
    media.fetchDocuments.mockResolvedValue({ items: [document] })
    expect(await resolveDocumentEntry({ library: 'lib', documentId: 'archive' })).toEqual({ document, page: undefined })
  })
  it('resolves old archive IDs and orphan pages without conflating libraries', async () => {
    media.fetchPages.mockResolvedValue({ items: [page] })
    expect(await resolveDocumentEntry({ sourceId: 'archive' }, 'lib')).toEqual({ document: undefined, page })
    expect(media.fetchDocuments.mock.calls[1]![0]).toMatchObject({ 'filter.library': ['lib'], 'filter.document_id': ['archive'] })
    media.fetchDocuments.mockResolvedValue({ items: [{ ...document, library: 'other' }] })
    expect(await resolveDocumentEntry({ sourceId: 'source' }, 'lib')).toEqual({})
  })
  it('rejects unrelated document/page records from an unexpected response', async () => {
    media.fetchDocuments.mockResolvedValue({ items: [{ ...document, document_id: 'other' }] })
    media.fetchPages.mockResolvedValue({ items: [{ ...page, library: 'other' }] })
    expect(await resolveDocumentEntry({ library: 'lib', documentId: 'archive' })).toEqual({ document: undefined, page: undefined })
  })
})
