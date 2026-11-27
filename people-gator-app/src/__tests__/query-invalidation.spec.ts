import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type Options = { query?: Record<string, unknown>; signal?: AbortSignal; body?: unknown }

/** A fake API that counts requests and cancellations per endpoint. */
const api = vi.hoisted(() => {
  const state = {
    calls: {} as Record<string, number>,
    aborts: 0,
    pages: ['p1', 'p2'],
    userName: 'Rita Reviewer',
    fail: new Set<string>(),
  }
  const endpoint =
    (name: string | ((options: Options) => string), data: (options: Options) => unknown) =>
    (options: Options = {}) => {
      const key = typeof name === 'function' ? name(options) : name
      state.calls[key] = (state.calls[key] ?? 0) + 1
      options.signal?.addEventListener('abort', () => state.aborts++)
      if (state.fail.has(key)) return Promise.reject(new Error(`${key} failed`))
      return Promise.resolve({ data: data(options) })
    }
  return { state, endpoint }
})

vi.mock('@/client', () => {
  const { state, endpoint } = api
  const blob = () => new Blob(['bytes'])
  const page = (id: string) => ({ source_id: id, library: 'lib', page_id: id })
  const users = () => [{ user_id: 'u1', display_name: state.userName }]
  return {
    getPageRouteApiV1PagesPageSourceIdGet: endpoint('page', () => page('p1')),
    getPageImageByIdRouteApiV1PagesPageSourceIdImageGet: endpoint('pageImage', blob),
    getImageContentByIdRouteApiV1ImagesImageIdContentGet: endpoint('imageContent', blob),
    getFaceAlignedCropRouteApiV1FacesDetectionIdAlignedCropGet: endpoint('faceCrop', blob),
    listFacesRouteApiV1FacesGet: endpoint('faces', () => ({ items: [], cursor: null })),
    listTextMentionGroupsRouteApiV1TextMentionGroupsGet: endpoint('mentionGroups', () => ({
      items: [],
      cursor: null,
    })),
    getEntityRouteApiV1EntitiesEntityIdGet: endpoint('entity', () => ({ entity_id: 'e1' })),
    getPersonRouteApiV1PeopleEntityIdGet: endpoint('person', () => ({ entity_id: 'e1' })),
    listPagesRouteApiV1PagesGet: endpoint(
      ({ query }) => (query?.['filter.source_id'] ? 'pageLabels' : 'pageOptions'),
      ({ query }) => {
        const selected = query?.['filter.source_id'] as string[] | undefined
        const ids = state.pages.filter((id) => !selected || selected.includes(id))
        return { items: ids.map(page), cursor: null }
      },
    ),
    listUserFilterOptionsRouteApiV1UserFilterOptionsGet: endpoint(
      ({ query }) => (query?.q ? 'userLabel' : 'userOptions'),
      () => ({ items: users(), cursor: null }),
    ),
    patchFaceRouteApiV1FacesDetectionIdPatch: endpoint('patchFace', () => ({
      detection_id: 'f2',
    })),
    patchFaceBatchRouteApiV1FacesBatchPatch: endpoint('patchFaces', ({ body }) =>
      (body as { detection_id: string }[]).map((face) =>
        face.detection_id === 'gone' ? null : face,
      ),
    ),
    createFaceRouteApiV1FacesPost: endpoint('createFace', () => ({ detection_id: 'f3' })),
    deleteFaceRouteApiV1FacesDetectionIdDelete: endpoint('deleteFace', () => null),
    patchTextMentionRouteApiV1TextMentionsMentionIdPatch: endpoint('patchMention', () => ({
      mention_id: 'm1',
    })),
    patchTextMentionBatchRouteApiV1TextMentionsBatchPatch: endpoint('patchMentions', ({ body }) =>
      (body as { mention_id: string }[]).map((mention) =>
        mention.mention_id === 'gone' ? null : mention,
      ),
    ),
    createTextMentionRouteApiV1TextMentionsPost: endpoint('createMention', () => ({
      mention_id: 'm2',
    })),
    deleteTextMentionBatchRouteApiV1TextMentionsBatchDelete: endpoint('deleteMentions', () => 1),
    patchEntityRouteApiV1EntitiesEntityIdPatch: endpoint('patchEntity', () => ({
      entity_id: 'e1',
      name: 'Renamed',
    })),
    deleteEntitiesRouteApiV1EntitiesDelete: endpoint('deleteEntities', () => null),
    deletePageRouteApiV1PagesPageSourceIdDelete: endpoint('deletePage', () => {
      state.pages = state.pages.filter((id) => id !== 'p2')
      return null
    }),
    createPageRouteApiV1PagesPost: endpoint('createPage', () => {
      state.pages = [...state.pages, 'p3']
      return page('p3')
    }),
    deleteSourceRouteApiV1SourcesSourceIdDelete: endpoint('deleteSource', () => null),
    patchUserRouteApiV1UsersUserIdPatch: endpoint('patchUser', ({ body }) => {
      state.userName = (body as { display_name: string }).display_name
      return { user_id: 'u1', display_name: state.userName }
    }),
  }
})

import { useDeleteEntitiesMutation, useEntityQuery, usePatchEntityMutation } from '@/query/entities'
import { useVerifyLinkMutation } from '@/query/entity-links'
import {
  useAssignFaceMutation,
  useAssignFacesMutation,
  useCreateFaceMutation,
  useDeleteFaceMutation,
  useFaceAlignedCropQuery,
  useFaceListQuery,
  useReviewFacesMutation,
} from '@/query/faces'
import { invalidateOnce } from '@/query/invalidation'
import { queryKeys } from '@/query/keys'
import {
  useCreatePageMutation,
  useDeletePageMutation,
  useDeleteSourceMutation,
  useImageContentQuery,
  usePageImageQuery,
  usePageQuery,
} from '@/query/media'
import { useReviewMentionsMutation } from '@/query/mention-review'
import { usePersonQuery } from '@/query/people'
import {
  useActorLabels,
  usePeopleFilterOptions,
  useSourceLabels,
} from '@/query/people-filter-options'
import {
  useAssignTextMentionsMutation,
  useCreateTextMentionMutation,
  useDeleteTextMentionsMutation,
  useReassignTextMentionMutation,
  useTextMentionGroupsQuery,
} from '@/query/text-mentions'
import { usePatchUserMutation } from '@/query/users'

/** Mount active observers for a scan with a person, plus every mutation. */
function workspace() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  let mounted!: ReturnType<typeof setup>
  function setup() {
    usePageQuery('p1')
    usePageImageQuery('p1', 1024)
    useImageContentQuery('i1')
    useFaceAlignedCropQuery('f1', 256)
    useFaceListQuery({})
    useTextMentionGroupsQuery({})
    useEntityQuery('e1')
    usePersonQuery('e1')
    return {
      pageOptions: usePeopleFilterOptions('page', ''),
      pageLabels: useSourceLabels('page', ['p1', 'p2']),
      userOptions: usePeopleFilterOptions('user', ''),
      userLabels: useActorLabels('user', ['u1']),
      assignFace: useAssignFaceMutation(),
      assignFaces: useAssignFacesMutation(),
      reviewFaces: useReviewFacesMutation(),
      createFace: useCreateFaceMutation(),
      deleteFace: useDeleteFaceMutation(),
      verifyLink: useVerifyLinkMutation(),
      reassignMention: useReassignTextMentionMutation(),
      assignMentions: useAssignTextMentionsMutation(),
      createMention: useCreateTextMentionMutation(),
      deleteMentions: useDeleteTextMentionsMutation(),
      reviewMentions: useReviewMentionsMutation(),
      patchEntity: usePatchEntityMutation(),
      deleteEntities: useDeleteEntitiesMutation(),
      deletePage: useDeletePageMutation(),
      deleteSource: useDeleteSourceMutation(),
      createPage: useCreatePageMutation(),
      patchUser: usePatchUserMutation(),
    }
  }
  const wrapper = mount(
    defineComponent({
      setup() {
        mounted = setup()
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
  )
  return { client, wrapper, ...mounted }
}

type Workspace = ReturnType<typeof workspace>

const MEDIA_BYTES = ['pageImage', 'imageContent', 'faceCrop']
const EVIDENCE_VIEWS = ['page', 'faces', 'mentionGroups', 'entity', 'person']

/** Cached views nobody is showing: counts and names on media records and search. */
const INACTIVE_VIEWS = [
  queryKeys.documents.list({ limit: 1 }),
  queryKeys.sources.list({ limit: 1 }),
  queryKeys.images.list({ limit: 1 }),
  queryKeys.search.pages({ limit: 1 }),
]

function fetches(names: string[]) {
  return Object.fromEntries(names.map((name) => [name, api.state.calls[name]]))
}
const each = (names: string[], count: number) =>
  Object.fromEntries(names.map((name) => [name, count]))

let view: Workspace

beforeEach(async () => {
  Object.assign(api.state, {
    calls: {},
    aborts: 0,
    pages: ['p1', 'p2'],
    userName: 'Rita Reviewer',
    fail: new Set(),
  })
  view = workspace()
  await flushPromises()
  expect(fetches([...MEDIA_BYTES, ...EVIDENCE_VIEWS])).toEqual(
    each([...MEDIA_BYTES, ...EVIDENCE_VIEWS], 1),
  )
})

afterEach(() => {
  view.wrapper.unmount()
  view.client.clear()
})

describe('evidence and identity mutations (#74)', () => {
  const mutations: [string, (view: Workspace) => Promise<unknown>][] = [
    ['assigning a face', (v) => v.assignFace.mutateAsync({ detectionId: 'f2', entityId: 'e1' })],
    [
      'assigning faces in bulk',
      (v) => v.assignFaces.mutateAsync({ detectionIds: ['f2'], entityId: 'e1' }),
    ],
    [
      'verifying faces',
      (v) => v.reviewFaces.mutateAsync({ detectionIds: ['f2'], action: 'verify' }),
    ],
    ['creating a face', (v) => v.createFace.mutateAsync({ entity_id: 'e1' } as never)],
    ['deleting a face', (v) => v.deleteFace.mutateAsync('f2')],
    ['verifying a face link', (v) => v.verifyLink.mutateAsync({ kind: 'face', id: 'f2' })],
    ['verifying a mention link', (v) => v.verifyLink.mutateAsync({ kind: 'mention', id: 'm1' })],
    [
      'reassigning a mention',
      (v) => v.reassignMention.mutateAsync({ mentionId: 'm1', entityId: 'e1' }),
    ],
    [
      'assigning mentions in bulk',
      (v) => v.assignMentions.mutateAsync({ mentionIds: ['m1'], entityId: 'e1' }),
    ],
    ['creating a mention', (v) => v.createMention.mutateAsync({ entity_id: 'e1' } as never)],
    ['deleting mentions', (v) => v.deleteMentions.mutateAsync(['m1'])],
    [
      'reviewing mentions',
      (v) => v.reviewMentions.mutateAsync({ targets: { ids: ['m1'] }, action: 'verify' }),
    ],
    ['deleting people in bulk', (v) => v.deleteEntities.mutateAsync({} as never)],
  ]

  it.each(mutations)(
    '%s refreshes each dependent view once and keeps image bytes',
    async (_name, mutate) => {
      for (const key of INACTIVE_VIEWS) view.client.setQueryData(key, {})
      await mutate(view)
      await flushPromises()
      for (const key of INACTIVE_VIEWS)
        expect(view.client.getQueryState(key)?.isInvalidated).toBe(true)
      expect(fetches(EVIDENCE_VIEWS)).toEqual(each(EVIDENCE_VIEWS, 2))
      expect(fetches(MEDIA_BYTES)).toEqual(each(MEDIA_BYTES, 1))
      expect(api.state.aborts).toBe(0)
    },
  )

  it('refreshes only the typed person record after an entity edit', async () => {
    await view.patchEntity.mutateAsync({ entityId: 'e1', body: { name: 'Renamed' } as never })
    await flushPromises()
    // The edited detail is stored from the response instead of being fetched again.
    expect(view.client.getQueryData(queryKeys.entities.detail('e1'))).toMatchObject({
      name: 'Renamed',
    })
    expect(fetches(EVIDENCE_VIEWS)).toEqual({ ...each(EVIDENCE_VIEWS, 2), entity: 1 })
    expect(fetches(MEDIA_BYTES)).toEqual(each(MEDIA_BYTES, 1))
    expect(api.state.aborts).toBe(0)
  })

  it.each([
    [
      'face review',
      (v: Workspace) =>
        v.reviewFaces.mutateAsync({ detectionIds: ['f2', 'gone'], action: 'verify' }),
    ],
    [
      'mention assignment',
      (v: Workspace) =>
        v.assignMentions.mutateAsync({ mentionIds: ['m1', 'gone'], entityId: 'e1' }),
    ],
    [
      'mention review',
      (v: Workspace) =>
        v.reviewMentions.mutateAsync({ targets: { ids: ['m1', 'gone'] }, action: 'unlink' }),
    ],
  ])('still refreshes once after a partially failed %s', async (_name, mutate) => {
    await expect(mutate(view)).rejects.toThrow()
    await flushPromises()
    expect(fetches(EVIDENCE_VIEWS)).toEqual(each(EVIDENCE_VIEWS, 2))
    expect(fetches(MEDIA_BYTES)).toEqual(each(MEDIA_BYTES, 1))
    expect(api.state.aborts).toBe(0)
  })

  it('leaves caches alone when the request is rejected', async () => {
    api.state.fail.add('patchFace')
    await expect(
      view.assignFace.mutateAsync({ detectionId: 'f2', entityId: 'e1' }),
    ).rejects.toThrow()
    await flushPromises()
    expect(fetches(EVIDENCE_VIEWS)).toEqual(each(EVIDENCE_VIEWS, 1))
  })

  it('marks inactive views stale without fetching them, and never image bytes', async () => {
    const inactive = [
      queryKeys.faces.list({ limit: 1 }),
      queryKeys.textMentions.groups({ limit: 1 }),
      queryKeys.entities.detail('e2'),
      queryKeys.pages.layout('p9'),
      queryKeys.search.pages({ limit: 1 }),
    ]
    const bytes = [
      queryKeys.pageImages.image('p9', 256),
      queryKeys.imageContents.content('i9'),
      queryKeys.faceCrops.aligned('f9', 256),
    ]
    for (const key of [...inactive, ...bytes]) view.client.setQueryData(key, {})
    const before = { ...api.state.calls }
    await view.assignFace.mutateAsync({ detectionId: 'f2', entityId: 'e1' })
    await flushPromises()
    for (const key of inactive) expect(view.client.getQueryState(key)?.isInvalidated).toBe(true)
    for (const key of bytes) expect(view.client.getQueryState(key)?.isInvalidated).toBe(false)
    expect(Object.keys(api.state.calls).filter((name) => !(name in before))).toEqual(['patchFace'])
  })
})

describe('overlapping invalidations (#74)', () => {
  it('refetches an active query once for duplicate and nested prefixes', async () => {
    await invalidateOnce(view.client, [
      queryKeys.faces.lists(),
      queryKeys.faces.all,
      queryKeys.pages.all,
      queryKeys.pages.detail('p1'),
      queryKeys.pages.all,
    ])
    expect(fetches(['faces', 'page'])).toEqual({ faces: 2, page: 2 })
    expect(api.state.aborts).toBe(0)
  })
})

describe('prefix deduplication (#74)', () => {
  it.each([
    ['an optional trailing part', [['a', undefined], ['a']], [['a', undefined]]],
    [
      'a narrower object filter first',
      [
        ['a', { x: 1, y: 2 }],
        ['a', { x: 1 }],
      ],
      [['a', { x: 1 }]],
    ],
    [
      'a narrower object filter last',
      [
        ['a', { x: 1 }],
        ['a', { x: 1, y: 2 }],
      ],
      [['a', { x: 1 }]],
    ],
    ['repeated nested prefixes', [['a', 'b'], ['a'], ['a', 'b'], ['a']], [['a']]],
    ['unrelated prefixes', [['a'], ['b']], [['a'], ['b']]],
  ])('keeps one covering key for %s', async (_name, groups, kept) => {
    const invalidate = vi.spyOn(view.client, 'invalidateQueries')
    await invalidateOnce(view.client, groups)
    expect(
      invalidate.mock.calls.map(
        ([filters]) => (typeof filters === 'function' ? filters() : filters)?.queryKey,
      ),
    ).toEqual(kept)
  })
})

describe('media mutations (#74)', () => {
  it('refreshes evidence, people, page choices and source labels after a deletion', async () => {
    expect(view.pageOptions.options.value.map((option) => option.id)).toEqual(['p1', 'p2'])
    expect(view.pageLabels.missing.value).toEqual([])
    const removed = queryKeys.pageImages.image('p2', 256)
    view.client.setQueryData(removed, new Blob())
    const inactive = [
      queryKeys.filterOptions.kind('library'),
      queryKeys.filterOptions.kind('document'),
      queryKeys.sourceLabels.selection('document', ['d1']),
    ]
    for (const key of inactive) view.client.setQueryData(key, {})

    await view.deletePage.mutateAsync('p2')
    await flushPromises()

    expect(fetches(EVIDENCE_VIEWS)).toEqual(each(EVIDENCE_VIEWS, 2))
    expect(fetches(['pageOptions', 'pageLabels'])).toEqual({ pageOptions: 2, pageLabels: 2 })
    expect(view.pageOptions.options.value.map((option) => option.id)).toEqual(['p1'])
    expect(view.pageLabels.labels.value).toEqual({ p1: 'lib / p1' })
    expect(view.pageLabels.missing.value).toEqual(['p2'])
    for (const key of inactive) expect(view.client.getQueryState(key)?.isInvalidated).toBe(true)
    // The deleted page's bytes are dropped; other images are not downloaded again.
    expect(view.client.getQueryData(removed)).toBeUndefined()
    expect(fetches(MEDIA_BYTES)).toEqual(each(MEDIA_BYTES, 1))
    expect(api.state.aborts).toBe(0)
  })

  it('drops both kinds of cached bytes for a deleted source', async () => {
    const bytes = [queryKeys.pageImages.image('s1', 256), queryKeys.imageContents.content('s1')]
    const kept = [queryKeys.pageImages.image('s2', 256), queryKeys.imageContents.content('s2')]
    for (const key of [...bytes, ...kept]) view.client.setQueryData(key, new Blob())
    await view.deleteSource.mutateAsync('s1')
    await flushPromises()
    for (const key of bytes) expect(view.client.getQueryData(key)).toBeUndefined()
    for (const key of kept) expect(view.client.getQueryData(key)).toBeDefined()
    expect(fetches(EVIDENCE_VIEWS)).toEqual(each(EVIDENCE_VIEWS, 2))
  })

  it('adds a created page to the page choices', async () => {
    await view.createPage.mutateAsync({} as never)
    await flushPromises()
    expect(view.pageOptions.options.value.map((option) => option.id)).toEqual(['p1', 'p2', 'p3'])
    expect(fetches(['pageOptions', 'pageLabels'])).toEqual({ pageOptions: 2, pageLabels: 2 })
    expect(fetches(MEDIA_BYTES)).toEqual(each(MEDIA_BYTES, 1))
    expect(api.state.aborts).toBe(0)
  })
})

describe('user mutations (#74)', () => {
  it('shows a renamed user in choices and selected labels', async () => {
    expect(view.userOptions.options.value).toEqual([{ id: 'u1', label: 'Rita Reviewer' }])
    expect(view.userLabels.labels.value).toEqual({ u1: 'Rita Reviewer' })
    const apiKeys = [...queryKeys.actorLabels.actor('api-key', 'k1')]
    view.client.setQueryData(apiKeys, 'Importer')

    const accounts = [queryKeys.users.list({ limit: 1 }), queryKeys.auth.me()]
    for (const key of [...INACTIVE_VIEWS, ...accounts]) view.client.setQueryData(key, {})

    await view.patchUser.mutateAsync({ userId: 'u1', body: { display_name: 'Rita Renamed' } })
    await flushPromises()

    expect(fetches(['userOptions', 'userLabel'])).toEqual({ userOptions: 2, userLabel: 2 })
    expect(view.userOptions.options.value).toEqual([{ id: 'u1', label: 'Rita Renamed' }])
    expect(view.userOptions.labels.value).toEqual({ u1: 'Rita Renamed' })
    expect(view.userLabels.labels.value).toEqual({ u1: 'Rita Renamed' })
    expect(view.client.getQueryState(apiKeys)?.isInvalidated).toBe(false)
    for (const key of [...INACTIVE_VIEWS, ...accounts])
      expect(view.client.getQueryState(key)?.isInvalidated).toBe(true)
    // Media records name their creator; faces, mentions and people do not.
    expect(fetches(EVIDENCE_VIEWS)).toEqual({ ...each(EVIDENCE_VIEWS, 1), page: 2 })
    expect(api.state.aborts).toBe(0)
  })
})
