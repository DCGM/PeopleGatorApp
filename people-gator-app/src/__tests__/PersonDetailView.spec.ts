import { mount, RouterLinkStub } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

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
    portrait: ref(''),
    portraitLoading: ref(false),
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
    processingRefreshing: ref(false),
    refreshProcessing: vi.fn<() => void>(),
    updateIdentifiers: vi.fn<() => void>(),
    updateProfile: vi.fn<() => void>(),
  }),
}))

vi.mock('@/viewmodels/person-discovery', () => ({
  usePersonDiscovery: () => ({
    assignFaces: vi.fn<() => void>(),
    assignmentStatus: ref('idle'),
    error: ref(null),
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
        plugins: [router],
        stubs: {
          RouterLink: RouterLinkStub,
          VerifyEntityLink: true,
          EvidenceFilterControls: true,
          EvidenceFilterTags: true,
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

    const stats = wrapper.get('aside[aria-label="Person statistics"]')
    expect(stats.text()).toContain('Last processed')
    expect(stats.text()).toContain('No processing recorded')
    expect(stats.get('details').attributes('open')).toBeDefined()
    expect(
      stats.get('button[aria-label="Hide processing information"]').attributes('aria-expanded'),
    ).toBe('true')
    await stats.get('button[aria-label="Hide processing information"]').trigger('click')
    expect(stats.text()).not.toContain('No processing recorded')
    expect(mentionLink?.props('to')).toEqual({
      name: 'document-page',
      params: { libraryId: 'nlp', documentId: 'document-1', pageId: 'page-1' },
      query: expect.objectContaining({ selectedPerson: 'person-ada' }),
    })
  })
})
