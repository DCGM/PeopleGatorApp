import { describe, expect, it } from 'vitest'

import type { EntityResponse, SearchEntitiesResult } from '@/client'
import {
  candidateEntities,
  candidateSearchParams,
  currentPagePersonIds,
} from '@/query/similar-people'

describe('similar-people search modes', () => {
  it('sends a face query only with no text, and switches to pure text when typing', () => {
    expect(candidateSearchParams('face-1', '')).toEqual({ q_face_id: ['face-1'], limit: 50 })
    expect(candidateSearchParams('face-1', '  Novak  ')).toEqual({ q: ['Novak'], limit: 50 })
    expect(candidateSearchParams(null, 'Novak')).toEqual({ q: ['Novak'], limit: 50 })
    expect(candidateSearchParams(null, '  ')).toBeUndefined()
  })

  it('classifies page membership using assigned faces and person mention spans', () => {
    expect(
      currentPagePersonIds(
        [{ entity_id: 'on-face' }, { entity_id: null }],
        [
          { entity_id: 'on-face', entity_type: 'person' },
          { entity_id: 'on-mention', entity_type: 'person' },
        { entity_id: 'not-person', entity_type: 'place' },
        ],
      ),
    ).toEqual(['on-face', 'on-mention'])
  })

  it('retains page identities without text, but uses only server matches with text', () => {
    const onPage = [{ entity_id: 'on-page', name: 'Anna' }] as EntityResponse[]
    const matches = [
      { entity_id: 'in-database', name: 'Johanna', aliases: ['Novak'], matching_score: 0.7 },
      { entity_id: 'on-page', name: 'Anna', matching_score: 0.6 },
    ] as SearchEntitiesResult[]

    expect(candidateEntities(onPage, matches, '').map((person) => person.entity_id)).toEqual([
      'in-database',
      'on-page',
    ])
    expect(candidateEntities(onPage, matches, 'Novak').map((person) => person.entity_id)).toEqual([
      'in-database',
      'on-page',
    ])
    expect(
      candidateEntities(onPage, [matches[0]!], 'Novak').map((person) => person.entity_id),
    ).toEqual(['in-database'])
    expect(candidateEntities(onPage, [], '').map((person) => person.entity_id)).toEqual(['on-page'])
  })
})
