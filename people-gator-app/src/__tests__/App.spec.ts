import { afterEach, describe, expect, it, vi } from 'vitest'

import { VueQueryPlugin } from '@tanstack/vue-query'
import Panzoom from '@panzoom/panzoom'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'

import App from '../App.vue'
import DocumentPageOverlay from '../components/custom/DocumentPageOverlay.vue'
import DocumentTeleprompter from '../components/custom/DocumentTeleprompter.vue'
import TopBar from '../components/custom/TopBar.vue'
import router from '../router'
import { readSharedFilters } from '@/viewmodels/shared-filters'

const documentWorkspaceMock = vi.hoisted(() => ({
  faces: [] as Array<Record<string, unknown>>,
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
    getScale: () => 0.82,
    getPan: () => ({ x: 0, y: 0 }),
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

vi.mock('@/viewmodels/document-list', async (original) => ({
  ...(await original<typeof import('@/viewmodels/document-list')>()),
  useDocumentList: () => ({
    documents: ref([]),
    resultCount: ref(0),
    filterError: ref(null),
    error: ref(null),
    isLoading: ref(false),
    hasNextPage: ref(false),
    isFetchingNextPage: ref(false),
    loadMore: vi.fn(),
    retry: vi.fn(),
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
    assignmentError: ref(null),
    createAndAssign: vi.fn<() => void>(),
    error: ref(null),
    annotationsLoading: ref(false),
    referenceFace: ref(null),
    faces: ref([]),
    isLoading: ref(false),
    page: ref(null),
    pageDimensions: ref({ width: 210, height: 297 }),
    pageImageLoading: ref(false),
    pageImageReady: ref(false),
    pageImageUrl: ref(''),
    transcription: ref(documentWorkspaceMock.transcription),
  }),
}))

enableAutoUnmount(afterEach)

describe('App', () => {
  it('keeps the logo when the optional top bar title is omitted', () => {
    const wrapper = mount(TopBar, { global: { plugins: [router, VueQueryPlugin] } })

    const logo = wrapper.get('a[aria-label="PeopleGator"] svg.lucide-people-gator')
    expect(logo.attributes('stroke-width')).toBe('1')
    expect(wrapper.get('nav').text()).not.toContain('People Gator')
  })

  it.each(['00000000-0000-4000-8000-000000000002', undefined])(
    'opens default People regardless of the current key selection: %s',
    async (currentKey) => {
      const originalKey = '00000000-0000-4000-8000-000000000001'
      await router.push({
        name: 'person-detail',
        params: { personId: 'irena' },
        query: {
          origin_return: `/people?q=Irena&api_key=${originalKey}`,
          api_key: originalKey,
          library: 'preview-mzk',
        },
      })
      const wrapper = mount(TopBar, { global: { plugins: [router, VueQueryPlugin] } })
      await router.push({ query: { ...router.currentRoute.value.query, api_key: currentKey } })
      await flushPromises()
      const crumb = wrapper.get('[aria-label="Breadcrumb"]').findAll('a')[1]!
      expect(
        wrapper
          .get('[aria-label="Breadcrumb"]')
          .findAll('a')
          .map((link) => link.text()),
      ).toEqual(['PeopleGator', 'People', 'irena'])
      expect(crumb.attributes('href')).not.toContain('origin_return')
      expect(wrapper.text()).not.toContain('Back to ')
      await crumb.trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.name).toBe('people-search')
      expect(readSharedFilters(router.currentRoute.value.query).apiKeyIds).toEqual([])
      expect(readSharedFilters(router.currentRoute.value.query).libraries).toEqual([])
      expect(router.currentRoute.value.query).not.toHaveProperty('origin_return')
      expect(router.currentRoute.value.query.q).toBeUndefined()
      wrapper.unmount()
    },
  )

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

  it('restores sidebar tabs from the URL, including former Activity and Statistics links', async () => {
    await router.push(
      '/libraries/library/documents/document/pages/page?panel=activity&candidate_text=Ada&origin_text=Irena',
    )
    const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })
    await flushPromises()
    const sidebar = wrapper.get('.workspace-sidebar')
    expect(sidebar.findAll('[role="tab"]').map((tab) => tab.text())).toEqual([
      'People',
      'Faces',
      'Mentions',
      'Info',
    ])
    expect(sidebar.get('[role="tab"][data-state="active"]').text()).toBe('Info')
    expect(sidebar.find('input[aria-label="Search people"]').exists()).toBe(false)

    await router.push({ query: { ...router.currentRoute.value.query, panel: 'statistics' } })
    await flushPromises()
    expect(sidebar.get('[role="tab"][data-state="active"]').text()).toBe('Info')

    await router.push({ query: { ...router.currentRoute.value.query, panel: undefined } })
    await flushPromises()
    expect(sidebar.get('[role="tab"][data-state="active"]').text()).toBe('People')
    expect(sidebar.get('input[aria-label="Search people"]').element).toHaveProperty('value', 'Ada')
    expect(router.currentRoute.value.query.candidate_text).toBe('Ada')
    // Never-applied origin text is dropped from copied links (#52).
    expect(router.currentRoute.value.query).not.toHaveProperty('origin_text')

    // Switching tabs keeps every other tab's settings.
    await router.push({ query: { ...router.currentRoute.value.query, panel: 'faces' } })
    await flushPromises()
    expect(sidebar.get('[role="tab"][data-state="active"]').text()).toBe('Faces')
    expect(router.currentRoute.value.query.candidate_text).toBe('Ada')
    await router.push({ path: router.currentRoute.value.path, hash: '#link-statistics' })
    await flushPromises()
    expect(sidebar.get('[role="tab"][data-state="active"]').text()).toBe('Info')
    wrapper.unmount()
  })

  it.each(['', '&page=bad-page&touched_from=bad-date'])(
    'keeps workspace filters out of the scan sidebar and its page toolbar (%s)',
    async (extra) => {
      await router.push(
        '/libraries/library/documents/document/pages/page?library=preview-mzk&link_state=manual&person=face-a&candidate_text=Ada' +
          extra,
      )
      const original = { ...router.currentRoute.value.query }
      const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })
      await flushPromises()
      const sidebar = wrapper.get('.workspace-sidebar')
      expect(sidebar.find('[aria-label="Active filters"]').exists()).toBe(false)
      expect(sidebar.find('[role="alert"]').exists()).toBe(false)
      expect(sidebar.text()).not.toContain('Clear filters')
      expect(
        sidebar.get('input[aria-label="Search people"]').attributes('disabled'),
      ).toBeUndefined()
      expect(router.currentRoute.value.query).toEqual(original)
      const tools = wrapper.get('[aria-label="Scan tools"]')
      expect(tools.get('button[aria-label="Manual"]').attributes('data-state')).toBe('off')
      await tools.get('button[aria-label="Verified"]').trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.query).toMatchObject(original)
      expect(router.currentRoute.value.query.page_link_state).toEqual(['verified'])
      expect(router.currentRoute.value.query.link_state).toBe('manual')
      wrapper.unmount()
    },
  )

  it('links breadcrumbs to scoped scan lists and preserves scope when searching', async () => {
    const archive = '00000000-0000-4000-8000-00000000000d'
    await router.push(`/libraries/library/documents/${archive}/pages/page`)
    const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })
    await flushPromises()

    const crumbs = wrapper.get('[aria-label="Breadcrumb"]').findAll('a')
    expect(crumbs.map((crumb) => crumb.text())).toEqual([
      'PeopleGator',
      'library',
      archive,
      'Page page',
    ])
    expect(crumbs[0]!.attributes('href')).toBe('/documents')
    expect(crumbs[1]!.attributes('href')).toContain('library=library')
    expect(crumbs[3]!.attributes('aria-current')).toBe('page')
    await crumbs[2]!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      library: 'library',
      archive_document: archive,
    })
    expect(wrapper.get('h1').text()).toBe('Document pages')
    await wrapper
      .get('input[placeholder="Search a person, page or document…"]')
      .setValue('archives')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      library: 'library',
      archive_document: archive,
      q: 'archives',
    })
    expect(
      wrapper
        .get('[aria-label="Breadcrumb"]')
        .findAll('a')
        .map((crumb) => crumb.text()),
    ).toEqual(['PeopleGator', 'Scans'])
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

    // The selected person's mentions use the scan overlay's orange highlight.
    const spans = wrapper.findAll('mark.transcription-entity')
    expect(spans.map((span) => span.attributes('data-selection'))).toEqual([
      'mentioned',
      'default',
      'mentioned',
    ])
    expect(spans[0]!.classes()).toEqual(
      expect.arrayContaining(['bg-orange-500/15', 'outline-orange-500']),
    )
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

    await wrapper.get('[aria-label="Search people"]').setValue('Grace')
    await wrapper.vm.$nextTick()
    await wrapper.get('mark.transcription-entity').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.selectedPerson).toBe('person-ada')
    expect(router.currentRoute.value.query.line).toBe('line-ada')
    // Selecting evidence no longer resets People search.
    expect(wrapper.get('[aria-label="Search people"]').element).toHaveProperty('value', 'Grace')
    documentWorkspaceMock.faces = []
    documentWorkspaceMock.transcription = []
  })

  it('preserves a page scope when editing scan search', async () => {
    await router.push('/scans?q=history&page=00000000-0000-4000-8000-000000000007')
    const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })

    expect(wrapper.find('[data-slot="pagination"]').exists()).toBe(false)
    await wrapper
      .get('input[placeholder="Search a person, page or document…"]')
      .setValue('archives')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({
      q: 'archives',
      page: '00000000-0000-4000-8000-000000000007',
    })
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
  it('activates independent tabs with fresh default destinations', async () => {
    await router.push('/scans?library=mzk&document=album&q=Ada&assignment=faces')
    const wrapper = mount(TopBar, { global: { plugins: [router, VueQueryPlugin] } })
    expect(wrapper.get('a[aria-label="Scans"]').attributes('aria-current')).toBe('page')
    expect(wrapper.get('a[aria-label="Documents"]').attributes('aria-current')).toBeUndefined()
    expect(wrapper.get('a[aria-label="Scans"]').attributes('href')).toBe('/scans')
    await router.push('/documents?library=mzk')
    expect(document.title).toBe('Documents | People Gator')
    expect(wrapper.get('a[aria-label="Documents"]').attributes('aria-current')).toBe('page')
    expect(wrapper.get('a[aria-label="Scans"]').attributes('aria-current')).toBeUndefined()
    expect(wrapper.get('a[aria-label="Scans"]').attributes('href')).toBe('/scans')
    expect(
      wrapper
        .get('[aria-label="Breadcrumb"]')
        .findAll('a')
        .map((node) => node.text()),
    ).toEqual(['PeopleGator', 'Documents'])
    await router.push('/libraries/mzk/documents/album/pages/scan')
    expect(wrapper.get('a[aria-label="Scans"]').attributes('aria-current')).toBe('page')
    // Top-level navigation adds no implicit scope for the opened page.
    expect(wrapper.get('a[aria-label="Scans"]').attributes('href')).toBe('/scans')
    wrapper.unmount()
  })

  it('removes scoped scan badges and clears filters atomically while preserving text', async () => {
    const doc = '00000000-0000-4000-8000-00000000000d'
    await router.push(`/scans?q=Ada&library=a&document=${doc}&assignment=faces&link_state=verified`)
    const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })
    await flushPromises()
    await wrapper.get(`button[aria-label="Remove Document: ${doc}"]`).trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.library).toEqual(['a'])
    expect(router.currentRoute.value.query.document).toBeUndefined()
    expect(router.currentRoute.value.query.link_state).toEqual(['verified'])
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Clear all filters')!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'Ada' })
    expect(wrapper.find('[aria-label="Active filters"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('resets multiple libraries in Documents and Scans navigation', async () => {
    await router.push('/documents?library=a&library=b')
    const wrapper = mount(TopBar, { global: { plugins: [router, VueQueryPlugin] } })
    expect(wrapper.get('a[aria-label="Documents"]').attributes('href')).toBe('/documents')
    expect(wrapper.get('a[aria-label="Scans"]').attributes('href')).toBe('/scans')
    expect(wrapper.findAll('[data-slot="breadcrumb-link"]').map((node) => node.text())).toEqual([
      'PeopleGator',
      'Documents',
    ])
    wrapper.unmount()
  })

  it.each(['/', '/unknown/nested/path'])(
    'opens Documents from %s and preserves the incoming query and hash',
    async (path) => {
      await router.push(`${path}?library=preview-mzk&evidence_key=selected#results`)
      const wrapper = mount(App, { global: { plugins: [router, VueQueryPlugin] } })
      await flushPromises()
      expect(router.currentRoute.value.name).toBe('document-list')
      expect(router.currentRoute.value.path).toBe('/documents')
      // A removed annotation-key criterion cannot silently become the
      // documents' own modification criterion.
      expect(router.currentRoute.value.query).toEqual({ library: 'preview-mzk' })
      expect(router.currentRoute.value.hash).toBe('#results')
      expect(document.title).toBe('Documents | People Gator')
      expect(wrapper.find('main h1').exists()).toBe(false)
      expect(wrapper.get('main header').text()).toBe('Documents index')
      expect(wrapper.get('a[aria-label="Documents"]').attributes('aria-current')).toBe('page')
      expect(wrapper.get('a[aria-label="Scans"]').attributes('aria-current')).toBeUndefined()
    },
  )

  it.each([
    '/scans?q=Ada&library=preview-mzk',
    '/libraries/preview-mzk/documents/album/pages/page',
    '/people/ada?evidence_library=preview-mzk',
  ])('opens Documents with either home control from %s', async (path) => {
    for (const control of ['logo', 'breadcrumb']) {
      await router.push(path)
      const wrapper = mount(TopBar, { global: { plugins: [router, VueQueryPlugin] } })
      const home =
        control === 'logo'
          ? wrapper.get('a[aria-label="PeopleGator"]')
          : wrapper.get('[aria-label="Breadcrumb"]').findAll('a')[0]!
      const expected = {}
      expect(home.attributes('href')).toBe(
        router.resolve({ name: 'document-list', query: expected }).href,
      )
      await home.trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.name).toBe('document-list')
      expect(router.currentRoute.value.query).toEqual(expected)
      expect(wrapper.get('a[aria-label="Documents"]').attributes('aria-current')).toBe('page')
      wrapper.unmount()
    }
  })

  it.each([
    ['/scans', 'document-search'],
    ['/documents', 'document-list'],
    ['/libraries/preview-mzk/documents/album/pages/page', 'document-page'],
    ['/people', 'people-search'],
    ['/people/ada', 'person-detail'],
  ])('loads explicit %s filters but does not forward them', async (path, name) => {
    await router.push(`${path}?evidence_library=preview-mzk&link_state=verified`)
    expect(router.currentRoute.value.name).toBe(name)
    expect(router.currentRoute.value.path).toBe(path)
    expect(router.currentRoute.value.query).toEqual({
      library: ['preview-mzk'],
      link_state: 'verified',
    })
    const wrapper = mount(TopBar, { global: { plugins: [router, VueQueryPlugin] } })
    await wrapper.get('a[aria-label="Scans"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('document-search')
    expect(readSharedFilters(router.currentRoute.value.query).libraries).toEqual([])
    expect(readSharedFilters(router.currentRoute.value.query).linkStates).toEqual([])
  })
})
