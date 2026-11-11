import { describe, expect, it } from 'vitest'
import {
  effectivePeopleOrder,
  peopleSearchChanges,
  resolveSearchModel,
  readSidebarState,
  sidebarQuery,
  sidebarSettingsQuery,
  type ScanSidebarState,
} from '@/viewmodels/scan-sidebar'

describe('scan sidebar URL state (#103)', () => {
  it('uses the agreed defaults when parameters are absent', () => {
    expect(readSidebarState({})).toEqual({
      tab: 'people',
      peopleText: '',
      searchFaceId: null,
      searchModel: null,
      peopleScope: 'document',
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
      peopleScope: 'document',
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

  it('defaults copied text/face searches to global similarity, preserving explicit URL choices', () => {
    for (const query of [{ candidate_text: ' Ada ' }, { candidate_face: 'face-a' }] as Record<
      string,
      string
    >[]) {
      expect(readSidebarState(query)).toMatchObject({
        peopleScope: 'all',
        peopleOrder: 'relevance',
      })
      expect(
        readSidebarState({ ...query, people_scope: 'page', candidate_sort: 'context' }),
      ).toMatchObject({ peopleScope: 'page', peopleOrder: 'context' })
    }
    expect(readSidebarState({ candidate_text: '  ' })).toMatchObject({
      peopleScope: 'document',
      peopleOrder: 'context',
    })
    // A nondefault explicit scope must survive URL serialization during search.
    expect(sidebarQuery({ peopleScope: 'document' }, { peopleText: 'Ada' })).toEqual({
      people_scope: 'document',
    })
    expect(sidebarQuery({ peopleScope: 'all' }, { peopleText: '' })).toEqual({
      people_scope: 'all',
    })
  })

  it('changes search mode only at input boundaries, allowing later explicit overrides', () => {
    const idle = readSidebarState({})
    const start = peopleSearchChanges(idle, { peopleText: 'Ada' })
    expect(start).toEqual({ peopleText: 'Ada', peopleScope: 'all', peopleOrder: 'relevance' })
    const searching = { ...idle, ...start }
    expect(peopleSearchChanges(searching, { peopleScope: 'page', peopleOrder: 'name' })).toEqual({
      peopleScope: 'page',
      peopleOrder: 'name',
    })
    expect(
      peopleSearchChanges({ ...searching, peopleScope: 'page' }, { peopleText: 'Adaline' }),
    ).toEqual({ peopleText: 'Adaline' })
    expect(peopleSearchChanges(searching, { peopleText: '  ' })).toEqual({
      peopleText: '  ',
      peopleScope: 'document',
      peopleOrder: 'context',
    })
    const combined = { ...searching, searchFaceId: 'f' }
    expect(peopleSearchChanges(combined, { peopleText: '' })).toEqual({ peopleText: '' })
    expect(peopleSearchChanges(combined, { searchFaceId: null })).toEqual({ searchFaceId: null })
    expect(peopleSearchChanges({ ...combined, peopleText: '' }, { searchFaceId: null })).toEqual({
      searchFaceId: null,
      peopleScope: 'document',
      peopleOrder: 'context',
    })
    expect(peopleSearchChanges(idle, { peopleText: ' ' })).toEqual({ peopleText: ' ' })
  })

  it('searches with the chosen model only when the attached face has it', () => {
    expect(resolveSearchModel('model-b', ['model-a', 'model-b'])).toBe('model-b')
    expect(resolveSearchModel('model-c', ['model-a', 'model-b'])).toBe('model-a')
    expect(resolveSearchModel(null, ['model-a'])).toBe('model-a')
    expect(resolveSearchModel('model-a', [])).toBeNull()
  })

  it('carries only sidebar settings to another scan page (#109)', () => {
    expect(
      sidebarSettingsQuery({
        panel: 'faces',
        face_scope: 'document',
        face_view: 'person',
        candidate_face: 'f',
        face_model: 'm',
        page_link_state: 'manual',
        library: 'lib',
        touched_by: 'u',
        person: 'f',
        line: 'l1',
        lines: 'person',
      }),
    ).toEqual({
      panel: 'faces',
      face_scope: 'document',
      face_view: 'person',
      candidate_face: 'f',
      face_model: 'm',
    })
  })

  it('falls back from Similarity to context order without a name or face', () => {
    expect(effectivePeopleOrder('relevance', false)).toBe('context')
    expect(effectivePeopleOrder('relevance', true)).toBe('relevance')
    expect(effectivePeopleOrder('name', false)).toBe('name')
  })
})
