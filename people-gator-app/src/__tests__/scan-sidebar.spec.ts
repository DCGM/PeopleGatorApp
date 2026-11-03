import { describe, expect, it } from 'vitest'
import {
  effectivePeopleOrder,
  resolveSearchModel,
  readSidebarState,
  sidebarQuery,
  type ScanSidebarState,
} from '@/viewmodels/scan-sidebar'

describe('scan sidebar URL state (#103)', () => {
  it('uses the agreed defaults when parameters are absent', () => {
    expect(readSidebarState({})).toEqual({
      tab: 'people',
      peopleText: '',
      searchFaceId: null,
      searchModel: null,
      peopleScope: 'all',
      peopleOrder: 'context',
      faceScope: 'page',
      faceView: 'flat',
      faceSort: { field: 'detection_id', direction: 'asc' },
      mentionScope: 'page',
      mentionView: 'group',
      mentionSort: { field: 'text', direction: 'asc' },
      mentionGroupSort: { field: 'text', direction: 'asc' },
      activityDirection: 'desc',
    } satisfies ScanSidebarState)
  })

  it('recovers safely from invalid and repeated values', () => {
    const state = readSidebarState({
      panel: 'faces-and-more',
      people_scope: ['page', 'document'],
      candidate_sort: 'random',
      face_scope: 'library',
      face_view: 'grid',
      mention_view: 'tree',
      activity_dir: 'sideways',
      face_sort: 'relevance',
    })
    expect(state).toMatchObject({
      tab: 'people',
      peopleScope: 'all',
      peopleOrder: 'context',
      faceScope: 'page',
      faceView: 'flat',
      mentionView: 'group',
      activityDirection: 'desc',
      faceSort: { field: 'detection_id', direction: 'asc' },
    })
  })

  it('keeps former Activity, Statistics and Similar faces links usable', () => {
    expect(readSidebarState({ panel: 'activity' }).tab).toBe('info')
    expect(readSidebarState({ panel: 'statistics' }).tab).toBe('info')
    expect(readSidebarState({}, '#link-statistics').tab).toBe('info')
    expect(readSidebarState({ candidate_mode: 'face', person: 'face-a' }).searchFaceId).toBe(
      'face-a',
    )
    expect(
      readSidebarState({ candidate_mode: 'face', person: 'face-a', candidate_face: 'face-b' })
        .searchFaceId,
    ).toBe('face-b')
    expect(readSidebarState({ candidate_mode: 'page', person: 'face-a' }).searchFaceId).toBeNull()
  })

  it('round-trips every setting and omits defaults from links', () => {
    const changed: Partial<ScanSidebarState> = {
      tab: 'mentions',
      peopleText: 'Novak',
      searchFaceId: 'face-a',
      searchModel: 'model-b',
      peopleScope: 'document',
      peopleOrder: 'relevance',
      faceScope: 'document',
      faceView: 'person',
      faceSort: { field: 'confidence', direction: 'asc' },
      mentionScope: 'document',
      mentionView: 'flat',
      mentionSort: { field: 'last_touched_at', direction: 'desc' },
      mentionGroupSort: { field: 'count', direction: 'desc' },
      activityDirection: 'asc',
    }
    const query = Object.fromEntries(
      Object.entries(sidebarQuery(changed)).filter(([, value]) => value !== undefined),
    ) as Record<string, string>
    expect(readSidebarState(query)).toEqual({ ...readSidebarState({}), ...changed })
    const defaults = sidebarQuery(readSidebarState({}))
    expect(Object.values(defaults).every((value) => value === undefined)).toBe(true)
    // Choosing a face replaces a former mode parameter.
    expect(sidebarQuery({ searchFaceId: 'face-a' })).toEqual({
      candidate_face: 'face-a',
      candidate_mode: undefined,
    })
  })

  it('searches with the chosen model only when the attached face has it', () => {
    expect(resolveSearchModel('model-b', ['model-a', 'model-b'])).toBe('model-b')
    expect(resolveSearchModel('model-c', ['model-a', 'model-b'])).toBe('model-a')
    expect(resolveSearchModel(null, ['model-a'])).toBe('model-a')
    expect(resolveSearchModel('model-a', [])).toBeNull()
  })

  it('falls back from Similarity to context order without a name or face', () => {
    expect(effectivePeopleOrder('relevance', false)).toBe('context')
    expect(effectivePeopleOrder('relevance', true)).toBe('relevance')
    expect(effectivePeopleOrder('name', false)).toBe('name')
  })
})
