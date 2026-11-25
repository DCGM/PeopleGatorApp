import { describe, expect, it } from 'vitest'

import { formatLifeDate, lifeDatesError, lifeSpan, parseIsoDate } from '@/lib/life-dates'

describe('life dates', () => {
  it('summarizes full, partial and unknown life spans', () => {
    expect(lifeSpan('1890-03-14', '1962-11-02')).toBe('1890–1962')
    expect(lifeSpan('1948-06-01', null)).toBe('b. 1948')
    expect(lifeSpan(undefined, '1931-05-20')).toBe('d. 1931')
    expect(lifeSpan(null, null)).toBe('')
    expect(lifeSpan('0950-01-01', '1010-01-01')).toBe('950–1010')
  })

  it('accepts only real calendar dates', () => {
    expect(parseIsoDate('1890-03-14')).toBe('1890-03-14')
    expect(parseIsoDate('1900-02-29')).toBeUndefined()
    expect(parseIsoDate('1890-3-14')).toBeUndefined()
    expect(parseIsoDate('1890-03-14T00:00:00Z')).toBeUndefined()
    expect(parseIsoDate(['1890-03-14'])).toBeUndefined()
  })

  it('formats without shifting the calendar day', () => {
    expect(formatLifeDate('1890-03-14')).toContain('1890')
    expect(formatLifeDate('1890-03-14')).toMatch(/14/)
  })

  it('rejects death before birth', () => {
    expect(lifeDatesError('1900-01-02', '1900-01-01')).toBe(
      'Death date must not be before birth date.',
    )
    expect(lifeDatesError('1900-01-01', '1900-01-01')).toBeUndefined()
    expect(lifeDatesError('', '1900-01-01')).toBeUndefined()
    expect(lifeDatesError('1900-13-01', '')).toBe('Enter a valid date.')
  })
})
