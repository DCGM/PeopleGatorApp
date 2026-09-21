import { describe, expect, it } from 'vitest'

import { sourceEntityNames } from '@/viewmodels/document-search'

describe('sourceEntityNames', () => {
  it('keeps only the first three unique names for the current source', () => {
    expect(
      sourceEntityNames([
        { name: 'Ada' },
        { name: 'Ada' },
        { name: 'Grace' },
        { name: 'Alan' },
        { name: 'Grace' },
        { name: null },
        { name: '  ' },
      ]),
    ).toEqual(['Ada', 'Grace', 'Alan'])
  })
})
