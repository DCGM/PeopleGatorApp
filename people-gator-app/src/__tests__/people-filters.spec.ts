import { describe, expect, it } from 'vitest'
import type { LocationQuery } from 'vue-router'
import {
  emptyPeopleFilters,
  localTimeToUtc,
  utcToLocalTime,
  peopleFiltersQuery,
  peopleFiltersUrl,
  readPeopleFilters,
  processingFilterError,
} from '@/viewmodels/people-filters'

describe('processing filter state', () => {
  it('converts local wall-clock input to UTC and restores it without precision loss', () => {
    const utc = '2026-01-02T12:30:15.123Z'
    expect(localTimeToUtc(utcToLocalTime(utc))).toBe(utc)
    expect(utcToLocalTime('2026-01-02T13:30:15.123+01:00')).toBe(utcToLocalTime(utc))
    expect(localTimeToUtc('')).toBeUndefined()
    expect(utcToLocalTime('not-a-date')).toBe('')
    expect(utcToLocalTime('2026-01-02T12:00')).toBe('')
  })

  it('keeps open inclusive boundaries and validates inverted ranges', () => {
    const filters = { ...emptyPeopleFilters(), touchedFrom: utcToLocalTime('2026-01-02T12:00:00Z') }
    expect(processingFilterError(filters)).toBeUndefined()
    expect(peopleFiltersQuery(filters)).toEqual({
      'filter.last_touched_from': '2026-01-02T12:00:00.000Z',
    })
    filters.touchedTo = filters.touchedFrom
    expect(processingFilterError(filters)).toBeUndefined()
    filters.touchedTo = utcToLocalTime('2026-01-02T11:59:00Z')
    expect(processingFilterError(filters)).toContain('before or equal')
  })

  it('round-trips every filter through a shareable URL and normalizes repeated IDs', () => {
    const filters = {
      touchedFrom: utcToLocalTime('2026-01-02T12:00:00Z'),
      touchedTo: '',
      documentIds: ['doc-2', 'doc-1'],
      userIds: ['user'],
      apiKeyIds: ['key'],
    }
    const restored = readPeopleFilters(peopleFiltersUrl(filters) as LocationQuery)
    expect(restored).toEqual({ ...filters, documentIds: ['doc-1', 'doc-2'] })
    expect(
      readPeopleFilters({ document: ['doc', 'doc', null], touched_by: 'user', api_key: '' }),
    ).toEqual({ ...emptyPeopleFilters(), documentIds: ['doc'], userIds: ['user'] })
    expect(peopleFiltersQuery(emptyPeopleFilters())).toEqual({})
  })
})
