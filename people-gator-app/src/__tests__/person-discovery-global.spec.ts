import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { toValue } from 'vue'
import { expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  faces: vi.fn(),
  people: vi.fn(),
  detail: vi.fn(),
  assign: vi.fn(),
  merge: vi.fn(),
}))
vi.mock('@/client', async (original) => ({
  ...(await original<object>()),
  searchFacesGetApiV1SearchFacesGet: api.faces,
  searchEntitiesGetApiV1SearchEntitiesGet: api.people,
}))
vi.mock('@/query/entities', async () => {
  const { ref } = await import('vue')
  return {
    fetchEntity: vi.fn(),
    useMergeEntitiesMutation: () => ({ status: ref('idle'), mutate: api.merge }),
  }
})
vi.mock('@/query/faces', async () => {
  const { ref } = await import('vue')
  return {
    fetchFaceAlignedCrop: vi.fn().mockResolvedValue(new Blob()),
    useAssignFacesMutation: () => ({ status: ref('idle'), mutate: api.assign }),
  }
})
vi.mock('@/query/face-models', async () => {
  const { ref } = await import('vue')
  return { useFaceModels: () => ({ data: ref({ items: [] }), error: ref(null) }) }
})
vi.mock('@/viewmodels/person-detail', async () => {
  const { ref } = await import('vue')
  return {
    usePersonDetail: (...args: unknown[]) => {
      api.detail(...args)
      return {
        entity: ref({ entity_id: 'current' }),
        error: ref(null),
        isLoading: ref(false),
        faceCount: ref(1),
        faceEmbeddingModel: ref('default'),
        faceIds: ref([]),
        faces: ref([]),
        mentions: ref([]),
        mentionCount: ref(0),
        libraryCount: ref(1),
        identifiers: ref({ wikidataId: '', nationalLibraryAuthorityId: '' }),
        profile: ref({ name: 'Reference', aliases: [], shortDescription: '', article: '' }),
        processing: ref({ touchedAt: null }),
      }
    },
  }
})
import PersonDetailView from '@/views/PersonDetailView.vue'
import PersonDiscoveryPanel from '@/components/custom/PersonDiscoveryPanel.vue'

it('discovers globally while preserving local state, explicit criteria, cache isolation and actions', async () => {
  const one = '00000000-0000-4000-8000-000000000001'
  const workspace = {
    library: 'local',
    document: one,
    page: one,
    touched_by: one,
    api_key: one,
    link_state: 'verified',
    touched_from: '2026-01-01T00:00:00Z',
    touched_to: '2026-01-02T00:00:00Z',
  }
  // Outside candidates disappear if any surrounding predicate leaks.
  api.faces.mockImplementation(({ query }) =>
    Promise.resolve({
      data: {
        items: Object.keys(query).some((k) => k.startsWith('filter.'))
          ? []
          : [
              { detection_id: 'outside-face', face_score: 0.9 },
              { detection_id: 'own-face', entity_id: 'current' },
            ],
        cursor: null,
      },
    }),
  )
  api.people.mockImplementation(({ query }) =>
    Promise.resolve({
      data: {
        items: Object.keys(query).some((k) => k.startsWith('filter.') && k !== 'filter.entity_type')
          ? []
          : [
              { entity_id: 'outside-person', entity_type: 'person', name: 'Outside' },
              { entity_id: 'current', entity_type: 'person' },
              { entity_id: 'place', entity_type: 'place' },
            ],
        cursor: null,
      },
    }),
  )
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/people/:personId', name: 'person-detail', component: PersonDetailView }],
  })
  await router.push({
    path: '/people/current',
    query: {
      ...workspace,
      tab: 'discover',
      discovery_annotations: 'name',
      discovery_model: 'chosen',
      discovery_text: 'extra',
      similar_sort: 'confidence',
      similar_dir: 'asc',
      people_sort: 'name',
      people_dir: 'desc',
    },
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(PersonDetailView, {
    global: {
      plugins: [router, [VueQueryPlugin, { queryClient: client }]],
      stubs: {
        RouterLink: RouterLinkStub,
        PersonPortrait: true,
        VerifyEntityLink: true,
        PersonFacesPanel: true,
        SharedFilterControls: true,
        SharedFilterTags: true,
        PersonDiscoveryPanel: true,
      },
    },
  })
  await flushPromises()
  const panel = () => wrapper.getComponent(PersonDiscoveryPanel)
  expect(
    panel()
      .props('faces')
      .map((f: { id: string }) => f.id),
  ).toEqual(['outside-face'])
  expect(
    panel()
      .props('people')
      .map((p: { id: string }) => p.id),
  ).toEqual(['outside-person'])
  const signals = {
    'query.entity_id': 'current',
    'query.entity_annotations': ['faces'],
    'query.face_embedding_model': 'chosen',
    limit: 40,
    cursor: null,
  }
  expect(api.faces.mock.lastCall?.[0].query).toEqual({
    ...signals,
    limit: 14,
    return_total_count: true,
    sort: 'confidence',
    sort_direction: 'asc',
  })
  expect(api.people.mock.lastCall?.[0].query).toEqual({
    ...signals,
    'query.entity_annotations': ['name'],
    'query.text': ['extra'],
    'filter.entity_type': ['person'],
    sort: 'name',
    sort_direction: 'desc',
  })
  const keys = () =>
    client
      .getQueryCache()
      .findAll({ queryKey: ['search'] })
      .map((q) => q.queryKey)
  const originalKeys = keys()
  // Ordinary Faces/Mentions still receive the workspace configuration.
  expect(toValue(api.detail.mock.lastCall![2])).toMatchObject({
    'filter.library': ['local'],
    'filter.document_source_id': [one],
    'filter.page_source_id': [one],
    'filter.entity_link_state': ['verified'],
    'filter.last_touched_by_user_id': [one],
    'filter.last_touched_by_api_key_id': [one],
  })
  panel().vm.$emit('assignFaces', ['outside-face', 'outside-face'])
  panel().vm.$emit('mergePeople', ['outside-person', 'outside-person', 'current'])
  expect(api.assign).toHaveBeenCalledWith({ detectionIds: ['outside-face'], entityId: 'current' })
  expect(api.merge).toHaveBeenCalledWith({
    targetEntityId: 'current',
    sourceEntityIds: ['outside-person'],
  })
  expect(router.currentRoute.value.query).toMatchObject(workspace)
  await router.replace({ query: { ...router.currentRoute.value.query, tab: 'faces' } })
  await flushPromises()
  expect(router.currentRoute.value.query).toMatchObject(workspace)
  await router.replace({
    query: { ...router.currentRoute.value.query, tab: 'discover', library: 'elsewhere' },
  })
  await flushPromises()
  expect(keys()).toEqual(originalKeys)
  expect(panel().props('faces')).toHaveLength(1)
  // Invalid surrounding filters cannot disable a global search either.
  await router.replace({
    query: { ...router.currentRoute.value.query, page: 'invalid', discovery_model: 'other' },
  })
  await flushPromises()
  expect(api.faces.mock.lastCall?.[0].query).toMatchObject({
    'query.face_embedding_model': 'other',
    cursor: null,
  })
  expect(api.people.mock.lastCall?.[0].query).toMatchObject({
    'query.face_embedding_model': 'other',
    cursor: null,
  })
  expect(keys()).toHaveLength(originalKeys.length + 2)
  // The two visible selector rows now control independent searches.
  const faceRequests = api.faces.mock.calls.length
  panel().vm.$emit('update:peopleFaceModel', 'people-only')
  await flushPromises()
  panel().vm.$emit('update:peopleAnnotations', ['name'])
  await flushPromises()
  expect(api.faces.mock.calls).toHaveLength(faceRequests)
  expect(api.people.mock.lastCall?.[0].query).toMatchObject({
    'query.face_embedding_model': 'people-only',
    'query.entity_annotations': ['name'],
    'query.text': ['extra'],
  })
  panel().vm.$emit('update:faceModel', 'faces-only')
  await flushPromises()
  expect(api.faces.mock.lastCall?.[0].query).toMatchObject({
    'query.face_embedding_model': 'faces-only',
  })
  expect(api.faces.mock.lastCall?.[0].query).not.toHaveProperty('query.text')
  expect(api.people.mock.lastCall?.[0].query).toMatchObject({
    'query.face_embedding_model': 'people-only',
  })
  expect(router.currentRoute.value.query).toMatchObject({
    people_model: 'people-only',
    people_annotations: ['name'],
    discovery_model: 'faces-only',
  })
  wrapper.unmount()
  client.clear()
})

it('loads the next face cursor, keeps prior results on failure and restarts assignment searches', async () => {
  const { defineComponent, ref } = await import('vue')
  const { usePersonDiscovery } = await import('@/viewmodels/person-discovery')
  const assigned = ref<'all' | 'unassigned'>('all')
  const response = ({ query }: { query: Record<string, unknown> }) =>
    Promise.resolve({
      data: {
        items: Array.from({ length: query.cursor ? 6 : 14 }, (_, i) => ({
          detection_id: `candidate-${query.cursor ? i + 14 : i}`,
          entity_id: null,
        })),
        total_count: 20,
        limit: 14,
        cursor: query.cursor ? null : 'opaque-next',
      },
    })
  api.faces.mockReset().mockImplementation(response)
  api.people.mockReset().mockResolvedValue({ data: { items: [], cursor: null } })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  let result!: ReturnType<typeof usePersonDiscovery>
  const wrapper = mount(
    defineComponent({
      setup() {
        result = usePersonDiscovery(
          'current',
          'model',
          '',
          true,
          undefined,
          undefined,
          undefined,
          undefined,
          assigned,
        )
        return () => null
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
  )
  await flushPromises()
  expect(result.similarFaces.value).toHaveLength(14)
  expect(result.foundFaceCount.value).toBe(20)
  expect(result.hasMoreFaces.value).toBe(true)
  await result.loadMoreFaces()
  await flushPromises()
  expect(api.faces.mock.lastCall?.[0].query).toMatchObject({
    cursor: 'opaque-next',
    limit: 14,
    return_total_count: true,
  })
  expect(new Set(result.similarFaces.value.map((face) => face.id)).size).toBe(20)
  expect(result.hasMoreFaces.value).toBe(false)
  assigned.value = 'unassigned'
  await flushPromises()
  expect(api.faces.mock.lastCall?.[0].query).toMatchObject({
    'filter.is_assigned': false,
    cursor: null,
  })
  expect(result.similarFaces.value).toHaveLength(14)
  api.faces.mockRejectedValueOnce(new Error('network'))
  await result.loadMoreFaces()
  await flushPromises()
  expect(result.moreFacesFailed.value).toBe(true)
  expect(result.similarFaces.value).toHaveLength(14)
  expect(result.searchError.value).toBeNull()
  await result.loadMoreFaces()
  await flushPromises()
  expect(result.moreFacesFailed.value).toBe(false)
  expect(result.similarFaces.value).toHaveLength(20)
  wrapper.unmount()
  client.clear()
})
