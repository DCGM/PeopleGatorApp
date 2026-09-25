import { describe, expect, it } from 'vitest'

import type { EntityResponse, FoundEntity } from '@/client'
import {
  candidateEntities,
  candidateSearchParams,
  currentPagePersonIds,
} from '@/viewmodels/similar-people'

describe('similar-people search modes', () => {
  it('sends a face query only with no text, and switches to pure text when typing', () => {
    expect(candidateSearchParams('face-1', '', 'face-model')).toEqual({
      'query.face_id': ['face-1'],
      'query.face_embedding_model': 'face-model',
      limit: 50,
    })
    expect(candidateSearchParams('face-1', '  Novak  ')).toEqual({
      'query.text': ['Novak'],
      limit: 50,
    })
    expect(candidateSearchParams(null, 'Novak')).toEqual({
      'query.text': ['Novak'],
      limit: 50,
    })
    expect(candidateSearchParams(null, '  ')).toBeUndefined()
    expect(candidateSearchParams('face-without-embedding', '')).toBeUndefined()
  })

  it('classifies page membership using assigned faces and person mention spans', () => {
    expect(
      currentPagePersonIds(
        [{ entity_id: 'on-face' }, { entity_id: null }],
        [
          { entity_id: 'on-face', entity_type: 'person' },
          { entity_id: 'on-mention', entity_type: 'person' },
        ],
      ),
    ).toEqual(['on-face', 'on-mention'])
  })

  it('retains page identities without text, but uses only server matches with text', () => {
    const onPage = [{ entity_id: 'on-page', name: 'Anna' }] as EntityResponse[]
    const matches = [
      {
        entity_id: 'in-database',
        entity_type: 'person',
        name: 'Johanna',
        aliases: ['Novak'],
        score: 0.7,
        text_score: 0.7,
        user_id: 'user-1',
      },
      {
        entity_id: 'on-page',
        entity_type: 'person',
        name: 'Anna',
        score: 0.6,
        text_score: 0.6,
        user_id: 'user-1',
      },
    ] as FoundEntity[]

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
