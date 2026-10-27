import { mount, RouterLinkStub } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'

import PersonDetailView from '@/views/PersonDetailView.vue'

vi.mock('@/viewmodels/person-detail', () => ({
  usePersonDetail: () => ({
    entity: ref({ entity_id: 'person-ada' }),
    error: ref(null),
    faceCount: ref(0),
    faceEmbeddingModel: ref(null),
    faceIds: ref([]),
    faces: ref([]),
    identifiers: ref({ wikidataId: '', nationalLibraryAuthorityId: '' }),
    isLoading: ref(false),
    libraryCount: ref(1),
    mentionCount: ref(1),
    mentions: ref([
      {
        id: 'mention-1',
        excerpt: 'Ada Lovelace wrote about the engine.',
        matchedText: 'Ada Lovelace',
        library: 'nlp',
        documentId: 'document-1',
        documentTitle: 'Document 1',
        pageId: 'page-1',
        pageLabel: '1',
      },
    ]),
    portraitFaceId: ref(undefined),
    profile: ref({
      name: 'Ada Lovelace',
      shortDescription: '',
      article: '',
      aliases: [],
    }),
    processing: ref({
      touchedAt: null,
      userId: null,
      userLabel: null,
      apiKeyId: null,
      apiKeyLabel: null,
    }),
    updateIdentifiers: vi.fn<() => void>(),
    updateProfile: vi.fn<() => void>(),
  }),
}))

vi.mock('@/query/face-models', () => ({
  useFaceModels: () => ({ data: ref({ items: [] }), error: ref(null), refetch: vi.fn() }),
}))

vi.mock('@/viewmodels/person-discovery', () => ({
  DISCOVERY_ANNOTATIONS: ['faces', 'aliases', 'name'],
  usePersonDiscovery: () => ({
    assignFaces: vi.fn<() => void>(),
    assignmentStatus: ref('idle'),
    searchError: ref(null),
    isLoadingFaces: ref(false),
    isLoadingPeople: ref(false),
    similarFaces: ref([]),
    similarPeople: ref([]),
  }),
}))

describe('PersonDetailView', () => {
  it('links mentions to the page with their person selected', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/people/:personId', name: 'person-detail', component: PersonDetailView },
        {
          path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
          name: 'document-page',
          component: { template: '<div />' },
        },
      ],
    })
    await router.push('/people/person-ada?tab=mentions')
    await router.isReady()

    const wrapper = mount(PersonDetailView, {
      global: {
        plugins: [router, [VueQueryPlugin, { queryClient: new QueryClient() }]],
        stubs: {
          RouterLink: RouterLinkStub,
          PersonPortrait: true,
          VerifyEntityLink: true,
          PersonFacesPanel: true,
          PersonMentionReviewList: {
            template:
              '<div><PersonMentionEntry v-for="mention in mentions" :key="mention.id" :mention="mention" :person-id="personId" :link-states="[]" /></div>',
            props: ['mentions', 'personId'],
            components: {
              PersonMentionEntry: (await import('@/components/custom/PersonMentionEntry.vue'))
                .default,
            },
          },
          SharedFilterControls: true,
          SharedFilterTags: true,
        },
      },
    })
    expect(
      wrapper.get('[aria-label="Person evidence panel"]').element.closest('template'),
    ).toBeNull()
    const mentionLink = wrapper.findAllComponents(RouterLinkStub).find((link) => {
      const target = link.props('to')
      return typeof target !== 'string' && target?.name === 'document-page'
    })

    expect(wrapper.get('[aria-label="Person identity"]').classes()).toContain('sticky')
    expect(wrapper.find('aside[aria-label="Person statistics"]').exists()).toBe(false)
    expect(wrapper.findAll('[role="tab"]').map((tab) => tab.text())).toEqual([
      'Faces 0',
      'Mentions 1',
      'Details',
      'Statistics',
    ])
    expect(mentionLink?.props('to')).toEqual({
      name: 'document-page',
      params: { libraryId: 'nlp', documentId: 'document-1', pageId: 'page-1' },
      query: expect.objectContaining({ selectedPerson: 'person-ada' }),
    })
  })
})

it('clears discovery source/model overrides together while keeping search and evidence URL state', async () => {
  const { flushPromises } = await import('@vue/test-utils')
  const { default: PersonDiscoveryPanel } =
    await import('@/components/custom/PersonDiscoveryPanel.vue')
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/people/:personId', name: 'person-detail', component: PersonDetailView }],
  })
  await router.push(
    '/people/person-ada?tab=discover&discovery_annotations=faces&discovery_model=alternate&discovery_text=extra&link_state=automatic&discovery_assignment=unassigned',
  )
  await router.isReady()
  const wrapper = mount(PersonDetailView, {
    global: {
      plugins: [router, [VueQueryPlugin, { queryClient: new QueryClient() }]],
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
  wrapper.getComponent(PersonDiscoveryPanel).vm.$emit('clearFilters')
  await flushPromises()
  expect(router.currentRoute.value.query).toEqual({
    tab: 'discover',
    discovery_text: 'extra',
    link_state: 'automatic',
    discovery_assignment: 'unassigned',
  })
  expect(wrapper.getComponent(PersonDiscoveryPanel).props('annotations')).toEqual([
    'faces',
    'aliases',
    'name',
  ])
  expect(wrapper.getComponent(PersonDiscoveryPanel).props('searchTerm')).toBe('extra')
  wrapper.unmount()
})
