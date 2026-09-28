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

  it('renders document controls inside the contextual top bar area', async () => {
    await router.push('/libraries/library/documents/document/pages/page')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })
    await flushPromises()
    const topBar = wrapper.get('nav')

    expect(topBar.text()).not.toContain('People Gator')
    expect(topBar.find('[aria-label="Previous line"]').exists()).toBe(true)
    expect(wrapper.get('main').find('[aria-label="Previous line"]').exists()).toBe(false)

    const badgeNamesToggle = topBar.get('[aria-label="Hide overlay badge names"]')
    expect(badgeNamesToggle.attributes('aria-pressed')).toBe('true')
    expect(wrapper.getComponent(DocumentPageOverlay).props('showBadgeNames')).toBe(true)

    await badgeNamesToggle.trigger('click')

    expect(topBar.get('[aria-label="Show overlay badge names"]').attributes('aria-pressed')).toBe(
      'false',
    )
    expect(wrapper.getComponent(DocumentPageOverlay).props('showBadgeNames')).toBe(false)
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
    await router.push('/documents?q=history&page=2')
    const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })

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
