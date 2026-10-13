import { describe, expect, it, vi } from 'vitest'

import { VueQueryPlugin } from '@tanstack/vue-query'
import Panzoom from '@panzoom/panzoom'
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'

import App from '../App.vue'
import DocumentPageOverlay from '../components/custom/DocumentPageOverlay.vue'
import DocumentTeleprompter from '../components/custom/DocumentTeleprompter.vue'
import TopBar from '../components/custom/TopBar.vue'
import router from '../router'

const documentWorkspaceMock = vi.hoisted(() => ({
  faces: [] as Array<Record<string, unknown>>,
  similarPeople: [] as Array<Record<string, unknown>>,
  transcription: [] as Array<{
    id: string
    text: string
    position: { left: number; top: number; width: number; height: number }
    entities: Array<{
      entity_id: string
      label: 'person'
      text: string
      line_id: string
      start_index: number
      end_index: number
    }>
  }>,
}))

vi.mock('@panzoom/panzoom', () => ({
  default: vi.fn<() => object>(() => ({
    destroy: vi.fn<() => void>(),
    reset: vi.fn<() => void>(),
    zoomIn: vi.fn<() => void>(),
    zoomOut: vi.fn<() => void>(),
    zoomWithWheel: vi.fn<() => void>(),
  })),
}))

vi.mock('@/viewmodels/document-search', () => ({
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

vi.mock('@/viewmodels/people-search', () => ({
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

vi.mock('@/viewmodels/person-detail', () => ({
  usePersonDetail: () => ({
    error: ref(null),
    faceCount: ref(0),
    faceIds: ref([]),
    faces: ref(documentWorkspaceMock.faces),
    identifiers: ref({ wikidataId: '', nationalLibraryAuthorityId: '' }),
    isLoading: ref(false),
    libraryCount: ref(0),
    mentionCount: ref(0),
    mentions: ref([]),
    portrait: ref(''),
    portraitLoading: ref(false),
    profile: ref({ name: '', shortDescription: '', article: '', aliases: [] }),
    updateIdentifiers: vi.fn<() => void>(),
    updateProfile: vi.fn<() => void>(),
  }),
}))

vi.mock('@/viewmodels/document-workspace', () => ({
  useDocumentWorkspace: () => ({
    assignFace: vi.fn<() => void>(),
    assignmentStatus: ref('idle'),
    createAndAssign: vi.fn<() => void>(),
    error: ref(null),
    faces: ref([]),
    hasNextPage: ref(false),
    isFetchingNextPage: ref(false),
    isLoading: ref(false),
    loadMore: vi.fn<() => void>(),
    pageDimensions: ref({ width: 210, height: 297 }),
    pageImageLoading: ref(false),
    pageImageUrl: ref(''),
    similarPeople: ref(documentWorkspaceMock.similarPeople),
    similarPeopleLoading: ref(false),
    transcription: ref(documentWorkspaceMock.transcription),
  }),
}))

describe('App', () => {
  it('keeps the logo when the optional top bar title is omitted', () => {
    const wrapper = mount(TopBar, { global: { plugins: [router] } })

    const logo = wrapper.get('a[aria-label="PeopleGator"] svg.lucide-people-gator')
    expect(logo.attributes('stroke-width')).toBe('1')
    expect(wrapper.get('nav').text()).not.toContain('People Gator')
  })

  it('renders floating document controls inside the viewer', async () => {
    await router.push('/libraries/library/documents/document/pages/page')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })
    await flushPromises()
    const topBar = wrapper.get('nav')

    expect(topBar.text()).not.toContain('People Gator')
    expect(topBar.find('[aria-label="Previous line"]').exists()).toBe(false)
    const tools = wrapper.get('.workspace-viewer [aria-label="Scan tools"]')
    expect(tools.find('[aria-label="Previous line"]').exists()).toBe(true)
    expect(wrapper.get('.panzoom-layer').find('[aria-label="Scan tools"]').exists()).toBe(false)

    const badgeNamesToggle = tools.get('[aria-label="Hide overlay badge names"]')
    expect(badgeNamesToggle.attributes('aria-pressed')).toBe('true')
    expect(wrapper.getComponent(DocumentPageOverlay).props('showBadgeNames')).toBe(true)

    await badgeNamesToggle.trigger('click')

    expect(tools.get('[aria-label="Show overlay badge names"]').attributes('aria-pressed')).toBe(
      'false',
    )
    expect(wrapper.getComponent(DocumentPageOverlay).props('showBadgeNames')).toBe(false)
  })

  it('links breadcrumbs to scoped scan lists and preserves scope when searching', async () => {
    await router.push('/libraries/library/documents/document/pages/page')
    const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })
    await flushPromises()

    const crumbs = wrapper.get('[aria-label="Breadcrumb"]').findAll('a')
    expect(crumbs.map((crumb) => crumb.text())).toEqual([
      'PeopleGator',
      'library',
      'document',
      'Page page',
    ])
    expect(crumbs[0]!.attributes('href')).toBe('/scans')
    expect(crumbs[1]!.attributes('href')).toBe('/scans?library=library')
    expect(crumbs[3]!.attributes('aria-current')).toBe('page')
    await crumbs[2]!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ library: 'library', document: 'document' })
    expect(wrapper.get('h1').text()).toBe('Document pages')
    await wrapper
      .get('input[placeholder="Search a person, page or document…"]')
      .setValue('archives')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      library: 'library',
      document: 'document',
      q: 'archives',
    })
    await wrapper.get('[aria-label="Breadcrumb"]').findAll('a')[1]!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ library: 'library' })
    expect(
      wrapper.get('input[placeholder="Search a person, page or document…"]').element,
    ).toHaveProperty('value', '')
    wrapper.unmount()
  })

  it('uses the full viewer layer as the panzoom coordinate space', async () => {
    await router.push('/libraries/library/documents/document/pages/page')
    const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })
    await flushPromises()

    const zoomLayer = wrapper.get('.panzoom-layer').element
    const calls = vi.mocked(Panzoom).mock.calls
    const latestCall = calls[calls.length - 1]

    expect(latestCall?.[0]).toBe(zoomLayer)
    expect(latestCall?.[1]).toMatchObject({ canvas: true, step: 0.45 })
    expect(zoomLayer.parentElement?.getAttribute('aria-label')).toBe('Pan and zoom document page')
    const overlay = wrapper.get('[data-slot="document-page-overlay"]').element
    expect(zoomLayer.contains(overlay)).toBe(false)
    expect(overlay.parentElement).toBe(zoomLayer.parentElement)
  })

  it('shows translated teleprompter text when translation is enabled', () => {
    const wrapper = mount(DocumentTeleprompter, {
      props: {
        transcription: [
          {
            id: 'line-1',
            text: 'Bonjour',
            position: { left: 0, top: 0, width: 50, height: 10 },
            entities: [],
          },
        ],
        selectedLineIndex: 0,
        selectedEntityKey: null,
        relatedEntityId: null,
        isTranslationOpen: true,
        selectedLanguage: 'en',
        currentTranslation: 'Hello',
      },
    })

    expect(wrapper.get('[aria-label="Translate teleprompter text"]').text()).toContain('en')
    expect(wrapper.text()).toContain('Hello')
    expect(wrapper.text()).toContain('Bonjour')
  })

  it('shows a skeleton while translation is loading', () => {
    const wrapper = mount(DocumentTeleprompter, {
      props: {
        transcription: [
          {
            id: 'line-1',
            text: 'Bonjour',
            position: { left: 0, top: 0, width: 50, height: 10 },
            entities: [],
          },
        ],
        selectedLineIndex: 0,
        selectedEntityKey: null,
        relatedEntityId: null,
        isTranslationOpen: true,
        selectedLanguage: 'en',
        translationLoading: true,
      },
    })

    expect(wrapper.get('[aria-label="Loading translation"]').attributes('aria-busy')).toBe('true')
    expect(wrapper.find('.animate-pulse').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('No translation available')
  })

  it('highlights every transcription span belonging to the selected person', () => {
    const wrapper = mount(DocumentTeleprompter, {
      props: {
        transcription: [
          {
            id: 'line-1',
            text: 'Ada met Grace',
            position: { left: 0, top: 0, width: 50, height: 10 },
            entities: [
              {
                entity_id: 'person-ada',
                label: 'person',
                text: 'Ada',
                line_id: 'line-1',
                start_index: 0,
                end_index: 3,
              },
              {
                entity_id: 'person-grace',
                label: 'person',
                text: 'Grace',
                line_id: 'line-1',
                start_index: 8,
                end_index: 13,
              },
            ],
          },
          {
            id: 'line-2',
            text: 'Ada wrote notes',
            position: { left: 0, top: 10, width: 50, height: 10 },
            entities: [
              {
                entity_id: 'person-ada',
                label: 'person',
                text: 'Ada',
                line_id: 'line-2',
                start_index: 0,
                end_index: 3,
              },
            ],
          },
        ],
        selectedLineIndex: 0,
        selectedEntityKey: null,
        relatedEntityId: 'person-ada',
      },
    })

    const spans = wrapper.findAll('mark.transcription-entity')
    expect(spans[0]?.attributes('style')).toContain('2px solid var(--accent)')
    expect(spans[1]?.attributes('style')).not.toContain('2px solid var(--accent)')
    expect(spans[2]?.attributes('style')).toContain('2px solid var(--accent)')
  })

  it('selects a person when its transcription span is clicked', async () => {
    documentWorkspaceMock.faces = [
      {
        id: 'face-ada',
        embeddingModel: 'face-model',
        personId: 'person-ada',
        name: 'Ada Lovelace',
        confidence: 98,
        status: 'assigned',
        position: { left: 0, top: 0, width: 10, height: 10 },
        portrait: '',
        portraitLoading: false,
      },
    ]
    documentWorkspaceMock.similarPeople = [
      {
        id: 'person-ada',
        name: 'Ada Lovelace',
        nerMentions: 1,
        detections: 1,
        source: 'page',
      },
    ]
    documentWorkspaceMock.transcription = [
      {
        id: 'line-ada',
        text: 'Ada Lovelace',
        position: { left: 0, top: 0, width: 50, height: 10 },
        entities: [
          {
            entity_id: 'person-ada',
            label: 'person',
            text: 'Ada Lovelace',
            line_id: 'line-ada',
            start_index: 0,
            end_index: 12,
          },
        ],
      },
    ]
    await router.push('/libraries/library/documents/document/pages/page?person=face-ada')
    const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })
    await flushPromises()

    await wrapper.get('[aria-label="Show people with similar faces"]').trigger('click')
    await wrapper.get('[aria-label="Search people"]').setValue('Grace')
    await wrapper.vm.$nextTick()
    await wrapper.get('mark.transcription-entity').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.selectedPerson).toBe('person-ada')
    expect(router.currentRoute.value.query.line).toBe('line-ada')
    expect(wrapper.get('[aria-label="Search people"]').element).toHaveProperty('value', '')
    expect(wrapper.get('[aria-label="Show people on this page"]').attributes('data-state')).toBe(
      'on',
    )
    documentWorkspaceMock.faces = []
    documentWorkspaceMock.similarPeople = []
    documentWorkspaceMock.transcription = []
  })

  it('removes page-number navigation from document search', async () => {
    await router.push('/scans?q=history&page=2')
    const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })

    expect(wrapper.find('[data-slot="pagination"]').exists()).toBe(false)
    await wrapper
      .get('input[placeholder="Search a person, page or document…"]')
      .setValue('archives')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ q: 'archives' })
  })

  it('defines all application pages', () => {
    expect(router.resolve({ name: 'document-search' }).path).toBe('/scans')
    expect(router.resolve({ name: 'document-list' }).path).toBe('/documents')
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

describe('Scans and Documents navigation', () => {
  it('activates independent tabs and keeps scan query filters', async () => {
    await router.push('/scans?library=mzk&document=album&q=Ada&assignment=faces')
    const wrapper = mount(TopBar, { global: { plugins: [router] } })
    expect(wrapper.get('a[aria-label="Scans"]').attributes('aria-current')).toBe('page')
    expect(wrapper.get('a[aria-label="Documents"]').attributes('aria-current')).toBeUndefined()
    expect(wrapper.get('a[aria-label="Scans"]').attributes('href')).toContain('assignment=faces')
    expect(wrapper.get('a[aria-label="Scans"]').attributes('href')).toContain('q=Ada')
    await router.push('/documents?library=mzk')
    expect(document.title).toBe('Documents | People Gator')
    expect(wrapper.get('a[aria-label="Documents"]').attributes('aria-current')).toBe('page')
    expect(wrapper.get('a[aria-label="Scans"]').attributes('aria-current')).toBeUndefined()
    expect(wrapper.get('a[aria-label="Scans"]').attributes('href')).toBe('/scans?library=mzk')
    expect(
      wrapper
        .get('[aria-label="Breadcrumb"]')
        .findAll('a')
        .map((node) => node.text()),
    ).toEqual(['PeopleGator', 'Documents', 'mzk'])
    await router.push('/libraries/mzk/documents/album/pages/scan')
    expect(wrapper.get('a[aria-label="Scans"]').attributes('aria-current')).toBe('page')
    expect(wrapper.get('a[aria-label="Scans"]').attributes('href')).toBe(
      '/scans?library=mzk&document=album',
    )
    wrapper.unmount()
  })

  it('keeps the default landing route on Scans', async () => {
    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/scans')
    expect(document.title).toBe('Scan search | People Gator')
  })
})
