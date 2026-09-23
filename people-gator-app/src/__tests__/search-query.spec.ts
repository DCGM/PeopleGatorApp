import { describe, expect, it } from 'vitest'

import { initialCursor, nextCursor, withCursor } from '@/query/cursor'
import { cursorResultPage } from '@/query/search'

describe('infinite search pagination', () => {
  it('uses a supplied cursor and defaults to null', () => {
    expect(initialCursor({ cursor: 'start' })).toBe('start')
    expect(initialCursor({})).toBeNull()
    expect(initialCursor()).toBeNull()
    expect(withCursor({ limit: 2 }, 'next')).toEqual({ limit: 2, cursor: 'next' })
    expect(nextCursor({ cursor: 'next' }, 'start')).toBe('next')
    expect(nextCursor({ cursor: 'next' }, 'next')).toBeNull()
    expect(nextCursor({ cursor: null }, 'start')).toBeNull()
  })

  it('maps the returned opaque cursor to the next page cursor', () => {
    expect(
      cursorResultPage({
        items: ['one'],
        total_count: 3,
        cursor: 'entity-1',
      }),
    ).toEqual({
      items: ['one'],
      totalCount: 3,
      nextPage: 'entity-1',
    })
    expect(cursorResultPage({ items: [], total_count: 3, cursor: null }).nextPage).toBeNull()
  })
})
