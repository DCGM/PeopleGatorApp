import { describe, expect, it } from 'vitest'
import {
  documentFilterError,
  documentFiltersQuery,
  documentFiltersUrl,
  emptyDocumentFilters,
  readDocumentFilters,
} from '@/viewmodels/document-filters'

it('roundtrips document filters and deduplicates multi-value URL selections', () => {
  const raw = {
    touched_from: '2026-01-01T12:34:56.123Z',
    touched_to: '2026-01-02T12:34:56.123Z',
    library: ['b', 'a', 'a'],
    touched_by: ['u1', 'u2'],
    api_key: ['k1'],
    link_state: ['verified', 'manual'],
    unassigned: 'no',
  }
  const filters = readDocumentFilters(raw)
  expect(filters.libraries).toEqual(['a', 'b'])
  expect(documentFilterError(filters)).toBeUndefined()
  expect(readDocumentFilters(documentFiltersUrl(filters) as typeof raw)).toEqual(filters)
  expect(documentFiltersQuery(filters)).toMatchObject({
    'filter.last_touched_from': raw.touched_from,
    'filter.last_touched_to': raw.touched_to,
    'filter.library': ['a', 'b'],
    'filter.last_touched_by_user_id': ['u1', 'u2'],
    'filter.last_touched_by_api_key_id': ['k1'],
    'filter.has_unassigned_faces': false,
  })
})
describe('document date bounds', () => {
  it('omits empty selections, includes a single bound and accepts equality', () => {
    expect(documentFiltersQuery(emptyDocumentFilters())).toEqual({})
    const filters = { ...emptyDocumentFilters(), touchedFrom: '2026-01-01T12:00:00' }
    expect(documentFilterError(filters)).toBeUndefined()
    expect(documentFiltersQuery(filters)['filter.last_touched_to']).toBeUndefined()
    expect(documentFilterError({ ...filters, touchedTo: filters.touchedFrom })).toBeUndefined()
  })
  it('rejects invalid or reversed time bounds', () => {
    expect(documentFilterError({ ...emptyDocumentFilters(), touchedFrom: 'invalid' })).toContain(
      'valid date',
    )
    expect(
      documentFilterError({
        ...emptyDocumentFilters(),
        touchedFrom: '2026-02-01T00:00',
        touchedTo: '2026-01-01T00:00',
      }),
    ).toContain('before or equal')
  })
})
