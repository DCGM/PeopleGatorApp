import { describe, expect, it } from 'vitest'
import {
  readUnassigned,
  readVerification,
  unassignedQuery,
  verificationQuery,
} from '@/viewmodels/document-filters'
import {
  readSharedFilters,
  sharedFilterError,
  sharedFiltersQuery,
} from '@/viewmodels/shared-filters'

const user = '00000000-0000-4000-8000-000000000002'

describe('document filters', () => {
  it('keeps the Documents-only face filter separate from the shared configuration', () => {
    expect(readUnassigned({ unassigned: 'no' })).toBe('no')
    expect(readUnassigned({ unassigned: 'other' })).toBe('all')
    expect(unassignedQuery('all')).toEqual({})
    expect(unassignedQuery('yes')).toEqual({ 'filter.has_unassigned_faces': true })
    const shared = readSharedFilters({
      unassigned: 'yes',
      library: ['b', 'a', 'a'],
      touched_by: user,
    })
    expect(sharedFiltersQuery(shared)).toEqual({
      'filter.library': ['a', 'b'],
      'filter.last_touched_by_user_id': [user],
    })
  })
  it('reads derived document verification from the URL (#149)', () => {
    expect(readVerification({ verification: 'verified' })).toBe('verified')
    expect(readVerification({ verification: 'not_verified' })).toBe('not_verified')
    expect(readVerification({ verification: 'partially' })).toBe('all')
    expect(verificationQuery('all')).toEqual({})
    expect(verificationQuery('not_verified')).toEqual({
      'filter.verification_state': ['not_verified'],
    })
  })
  it('accepts a single or equal bound and rejects invalid or reversed bounds', () => {
    const from = '2026-01-01T12:00:00'
    expect(sharedFilterError({ touchedFrom: from, touchedTo: '' })).toBeUndefined()
    expect(sharedFilterError({ touchedFrom: from, touchedTo: from })).toBeUndefined()
    expect(sharedFilterError({ touchedFrom: 'invalid', touchedTo: '' })).toContain('valid date')
    expect(
      sharedFilterError({ touchedFrom: '2026-02-01T00:00', touchedTo: '2026-01-01T00:00' }),
    ).toContain('before or equal')
  })
})
