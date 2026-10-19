import { describe, expect, it } from 'vitest'
import type { LocationQuery } from 'vue-router'
import {
  evidenceFiltersQuery,
  evidenceFiltersUrl,
  evidenceUrlError,
  readEvidenceFilters,
  relatedEvidenceQuery,
  returnLocation,
} from '@/viewmodels/evidence-filters'
const doc = '00000000-0000-4000-8000-000000000001'
const actor = '00000000-0000-4000-8000-000000000002'
const shared: LocationQuery = {
  link_state: ['verified', 'manual'],
  evidence_origin: ['authority', 'manual'],
  evidence_document: doc,
  evidence_library: 'preview-mzk',
  evidence_user: actor,
  evidence_from: '2026-01-01T12:00:00.123+02:00',
  evidence_to: '2026-01-01T10:00:00.123Z',
}

describe('shared annotation filters and scoped navigation', () => {
  it('normalizes local/UTC dates and repeated selections with inclusive equal bounds', () => {
    const filters = readEvidenceFilters(shared)
    const query = evidenceFiltersQuery(filters)
    expect(query['filter.evidence_touched_from']).toBe('2026-01-01T10:00:00.123Z')
    expect(query['filter.evidence_touched_to']).toBe(query['filter.evidence_touched_from'])
    expect(query['filter.document_source_id']).toEqual([doc])
    expect(query['filter.evidence_touched_by_user_id']).toEqual([actor])
    expect(query).not.toHaveProperty('filter.last_touched_from')
    expect(readEvidenceFilters(evidenceFiltersUrl(filters) as LocationQuery)).toEqual(filters)
  })
  it('retains active criteria across document → person → page and changing a shared choice', () => {
    const fromDocument = relatedEvidenceQuery({
      name: 'document-list',
      path: '/documents',
      query: {
        ...shared,
        q: 'Irena',
        touched_by: actor,
        touched_from: '2025-01-01T00:00:00Z',
        cursor: 'old',
      },
    }) as LocationQuery
    expect(fromDocument.evidence_document).toEqual([doc])
    expect(fromDocument.origin_source_touched_by).toBe(actor)
    expect(fromDocument.origin_source_touched_from).toBe('2025-01-01T00:00:00Z')
    expect(fromDocument).not.toHaveProperty('touched_from')
    expect(fromDocument).not.toHaveProperty('q')
    expect(fromDocument).not.toHaveProperty('cursor')
    expect(fromDocument.origin_text).toBe('Irena')
    expect(String(fromDocument.origin_return)).not.toContain('cursor')
    const fromPerson = relatedEvidenceQuery({
      name: 'person-detail',
      path: '/people/irena',
      query: { ...fromDocument, evidence_origin: 'automatic' },
    }) as LocationQuery
    expect(fromPerson.evidence_origin).toEqual(['automatic'])
    expect(fromPerson.origin_return).toBe(fromDocument.origin_return)
    expect(
      evidenceFiltersQuery(readEvidenceFilters(fromPerson))['filter.evidence_touched_by_user_id'],
    ).toEqual([actor])
  })
  it('keeps person dates, assignment and search context separate from evidence edits', () => {
    const query = relatedEvidenceQuery({
      name: 'people-search',
      path: '/people',
      query: {
        q: 'Irena',
        assignment: 'mentions',
        document: doc,
        touched_by: actor,
        touched_from: '2025-01-01T00:00:00Z',
      },
    }) as LocationQuery
    expect(query.tab).toBe('mentions')
    expect(query.evidence_document).toEqual([doc])
    expect(query.origin_person_touched_by).toBe(actor)
    expect(evidenceFiltersQuery(readEvidenceFilters(query))).not.toHaveProperty(
      'filter.evidence_touched_from',
    )
    expect(evidenceFiltersQuery(readEvidenceFilters(query))).not.toHaveProperty(
      'filter.evidence_touched_by_user_id',
    )
  })
  it('defines recoverable invalid bounds, selections and internal return links', () => {
    expect(evidenceUrlError({ ...shared, evidence_from: 'not-a-date' })).toContain(
      'Invalid annotation date',
    )
    expect(evidenceUrlError({ ...shared, evidence_from: '2027-01-01T00:00:00Z' })).toContain(
      'before or equal',
    )
    expect(evidenceUrlError({ evidence_user: 'missing' })).toContain('Invalid evidence identifier')
    expect(evidenceUrlError({ evidence_origin: 'verified' })).toContain('Invalid evidence origin')
    expect(returnLocation({ origin_return: '//example.invalid' })).toBeUndefined()
    expect(returnLocation({ origin_return: '/people?q=Irena' })).toBe('/people?q=Irena')
  })
})
