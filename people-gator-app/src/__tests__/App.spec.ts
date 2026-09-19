import { describe, expect, it, vi } from 'vitest'

import Panzoom from '@panzoom/panzoom'
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'

import App from '../App.vue'
import TopBar from '../components/custom/TopBar.vue'
import router from '../router'

vi.mock('@panzoom/panzoom', () => ({
  default: vi.fn<() => object>(() => ({
    destroy: vi.fn<() => void>(),
    reset: vi.fn<() => void>(),
    zoomIn: vi.fn<() => void>(),
    zoomOut: vi.fn<() => void>(),
    zoomWithWheel: vi.fn<() => void>(),
  })),
}))

vi.mock('@/query/document-search', () => ({
  useDocumentSearch: () => ({
    cards: ref([]),
    error: ref(null),
    hasNextPage: ref(false),
    isFetchingNextPage: ref(false),
    isLoading: ref(false),
    loadMore: vi.fn<() => void>(),
    resultCount: ref(26),
  }),
}))

vi.mock('@/query/people-search', () => ({
  usePeopleSearch: () => ({
    error: ref(null),
    hasNextPage: ref(false),
    isFetchingNextPage: ref(false),
    isLoading: ref(false),
    loadMore: vi.fn<() => void>(),
    people: ref([]),
    resultCount: ref(26),
  }),
}))

vi.mock('@/query/person-detail', () => ({
  usePersonDetail: () => ({
    error: ref(null),
    faces: ref([]),
    identifiers: ref({ wikidataId: '', nationalLibraryAuthorityId: '' }),
    isLoading: ref(false),
    libraryCount: ref(0),
    mentions: ref([]),
    portrait: ref(''),
    profile: ref({ name: '', shortDescription: '', article: '', aliases: [] }),
    updateProfile: vi.fn<() => void>(),
  }),
}))

vi.mock('@/query/document-workspace', () => ({
  useDocumentWorkspace: () => ({
    assignFace: vi.fn<() => void>(),
    assignmentStatus: ref('idle'),
    createAndAssign: vi.fn<() => void>(),
    error: ref(null),
    faces: ref([]),
    isLoading: ref(false),
    pageDimensions: ref({ width: 210, height: 297 }),
    pageImageUrl: ref(''),
    similarPeople: ref([]),
    similarPeopleLoading: ref(false),
    transcription: ref([]),
  }),
}))

describe('App', () => {
  it('keeps the logo when the optional top bar title is omitted', () => {
    const wrapper = mount(TopBar, { global: { plugins: [router] } })

    expect(wrapper.get('nav').text()).toContain('PG')
    expect(wrapper.get('nav').text()).not.toContain('People Gator')
  })

  it('renders document controls inside the contextual top bar area', async () => {
    await router.push('/libraries/library/documents/document/pages/page')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()
    const topBar = wrapper.get('nav')

    expect(topBar.text()).not.toContain('People Gator')
    expect(topBar.find('[aria-label="Previous line"]').exists()).toBe(true)
    expect(wrapper.get('main').find('[aria-label="Previous line"]').exists()).toBe(false)
  })

  it('uses the full viewer layer as the panzoom coordinate space', async () => {
    await router.push('/libraries/library/documents/document/pages/page')
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    const zoomLayer = wrapper.get('.panzoom-layer').element
    const calls = vi.mocked(Panzoom).mock.calls
    const latestCall = calls[calls.length - 1]

    expect(latestCall?.[0]).toBe(zoomLayer)
    expect(latestCall?.[1]).toMatchObject({ canvas: true })
    expect(zoomLayer.parentElement?.getAttribute('aria-label')).toBe('Pan and zoom document page')
  })

  it('removes page-number navigation from document search', async () => {
    await router.push('/documents?q=history&page=2')
    const wrapper = mount(App, { global: { plugins: [router] } })

    expect(wrapper.find('[data-slot="pagination"]').exists()).toBe(false)
    await wrapper
      .get('input[placeholder="Search a person, page or document…"]')
      .setValue('archives')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ q: 'archives' })
  })

  it('defines all application pages', () => {
    expect(router.resolve({ name: 'document-search' }).path).toBe('/documents')
    expect(router.resolve({ name: 'people-search' }).path).toBe('/people')
    expect(
      router.resolve({
        name: 'document-page',
        params: { libraryId: 'library', documentId: 'document', pageId: 'page' },
      }).path,
    ).toBe('/libraries/library/documents/document/pages/page')
    expect(router.resolve({ name: 'person-detail', params: { personId: 'person' } }).path).toBe(
      '/people/person',
    )
  })
})
