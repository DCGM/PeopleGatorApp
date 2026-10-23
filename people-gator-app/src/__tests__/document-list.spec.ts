import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  documents: vi.fn(),
  search: vi.fn(),
  libraries: vi.fn(),
  pages: vi.fn(),
  image: vi.fn(),
  entities: vi.fn(),
  detail: vi.fn(),
}))
vi.mock('@/client', () => ({
  listDocumentsRouteApiV1DocumentsGet: api.documents,
  searchDocumentsGetApiV1SearchDocumentsGet: api.search,
  documentLibraryFilterOptionsRouteApiV1DocumentLibraryFilterOptionsGet: api.libraries,
  listUserFilterOptionsRouteApiV1UserFilterOptionsGet: vi
    .fn()
    .mockResolvedValue({ data: { items: [] } }),
  listApiKeysRouteApiV1ApiKeysGet: vi.fn().mockResolvedValue({ data: { items: [] } }),
  listPagesRouteApiV1PagesGet: api.pages,
  getPageImageByIdRouteApiV1PagesPageSourceIdImageGet: api.image,
  listEntitiesRouteApiV1EntitiesGet: api.entities,
  getPageRouteApiV1PagesPageSourceIdGet: api.detail,
}))
const desktop = ref(true)
vi.mock('@vueuse/core', async (original) => ({
  ...(await original<typeof import('@vueuse/core')>()),
  useMediaQuery: () => desktop,
}))
import DocumentListView from '@/views/DocumentListView.vue'
import { documentTitle } from '@/viewmodels/document-list'
import { useDocumentSearch } from '@/viewmodels/document-search'

const doc = (library: string, id = 'shared', name: string | null = 'Album') => ({
  source_id: `${library}-${id}`,
  source_type: 'document',
  library,
  document_id: id,
  name,
  url: 'https://example.test',
})
const page = (library: string, id: string) => ({
  source_id: id,
  source_type: 'page',
  library,
  document_id: 'shared',
  page_id: id,
  url: 'https://example.test',
})
const response = (items: unknown[], total_count = items.length, cursor: string | null = null) => ({
  data: { items, total_count, cursor, limit: 12 },
})
const cleanups: Array<() => void> = []
// Previews are scoped by the internal document UUID (`<library>-<archive id>` here).
const lib = (query: Record<string, string[]>) =>
  query['filter.document_source_id']?.[0]?.split('-')[0] ?? query['filter.library']![0]!
const user = '00000000-0000-4000-8000-000000000002'
const key = '00000000-0000-4000-8000-000000000001'

async function render(url = '/documents') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/documents', name: 'document-list', component: DocumentListView },
      { path: '/scans', name: 'document-search', component: defineComponent(() => () => h('div')) },
      {
        path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
        name: 'document-page',
        component: defineComponent(() => () => h('div')),
      },
    ],
  })
  await router.push(url)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const wrapper = mount(DocumentListView, {
    global: { plugins: [router, [VueQueryPlugin, { queryClient }]] },
  })
  cleanups.push(() => {
    wrapper.unmount()
    queryClient.clear()
  })
  await flushPromises()
  return { wrapper, router, queryClient }
}

beforeEach(() => {
  vi.clearAllMocks()
  desktop.value = true
  api.libraries.mockResolvedValue(response([{ library: 'a' }, { library: 'b' }]))
  api.search.mockResolvedValue(response([doc('a')]))
  api.documents.mockResolvedValue(response([doc('a'), doc('b', 'shared', null)]))
  api.pages.mockImplementation(({ query }) =>
    Promise.resolve(response([page(lib(query), `${lib(query)}-1`)])),
  )
  api.image.mockRejectedValue(new Error('Missing thumbnail'))
  api.entities.mockResolvedValue(response([{ name: 'Ada' }, { name: 'Ada' }, { name: 'Grace' }]))
})
afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup()
})

describe('document search and bounded groups', () => {
  it('renders separate document rows, isolated previews, totals and both kinds of links', async () => {
    const counts = { total: 2, automatic: 1, manual: 0, verified: 1, unassigned: 0 }
    api.documents.mockResolvedValue(
      response([
        {
          ...doc('a'),
          last_touched_at: '2026-10-14T12:00:00Z',
          last_touched_by_user_id: 'review-user',
          last_touched_by_api_key_id: 'review-key',
          entity_link_stats: { faces: counts, mentions: counts },
        },
        doc('b', 'shared', null),
      ]),
    )
    const { wrapper } = await render()
    expect(wrapper.findAll('h2').map((node) => node.text())).toEqual(['Album', 'Document shared'])
    expect(
      [...wrapper.get('.document-pages').element.children].map((node) => node.tagName),
    ).toEqual(['ARTICLE', 'ARTICLE'])
    expect(wrapper.findAll('.scan-card').map((node) => node.attributes('href'))).toEqual([
      '/libraries/a/documents/shared/pages/a-1',
      '/libraries/b/documents/shared/pages/b-1',
    ])
    for (const [index, library] of ['a', 'b'].entries()) {
      const link = wrapper.findAll('.document-link')[index]!
      expect(link.attributes('href')).toBe(`/scans?document=${library}-shared`)
      expect(link.get('p').text()).toBe(`${library} · shared`)
      expect(link.attributes('aria-label')).toContain(`in ${library}`)
    }
    for (const card of wrapper.findAll('.scan-card'))
      expect(card.find('.font-bold.text-secondary').exists()).toBe(false)
    expect(wrapper.get('.document-link .text-secondary').classes()).toContain('font-bold')
    expect(wrapper.text()).toContain('Ada, Grace')
    expect(wrapper.text()).toContain('Processing not recorded')
    const information = wrapper.get('.document-heading')
    const lines = information.findAll('p').map((node) => node.text())
    expect(lines[1]).toBe('1 registered page')
    expect(lines[2]).toMatch(/^Last processed:/)
    expect(lines[3]).toBe('User: review-user')
    expect(lines[4]).toBe('API key: review-key')
    expect(information.element.lastElementChild?.getAttribute('aria-label')).toBe('Link statistics')
    expect(wrapper.get('[data-slot="input-group"] [role="status"]').text()).toBe('2 results')
    expect(api.detail).not.toHaveBeenCalled()
    for (const library of ['a', 'b'])
      expect(api.pages).toHaveBeenCalledWith(
        expect.objectContaining({
          query: {
            'filter.document_source_id': [`${library}-shared`],
            sort: 'page_id',
            limit: 4,
            return_total_count: true,
            cursor: null,
          },
        }),
      )
    expect(documentTitle({ document_id: 'legacy', name: ' ' })).toBe('Document legacy')
  })
  it.each(['', '?library=a'])('opens all document pages without implicit annotation filters: %s', async (query) => {
    const { wrapper, router } = await render('/documents' + query)
    const firstLink = wrapper.get('.document-link')
    expect(firstLink.attributes('href')).toBe(`/scans?${query ? 'library=a&' : ''}document=a-shared`)
    expect(wrapper.get('a.scan-card').attributes('href')).toBe(
      `/libraries/a/documents/shared/pages/a-1${query}`,
    )
    await firstLink.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      ...(query && { library: ['a'] }),
      document: 'a-shared',
    })
  })
  it('carries the shared configuration unchanged into document and scan links', async () => {
    const { wrapper, router } = await render(`/documents?library=a&api_key=${key}&link_state=verified&unassigned=yes&q=Album`)
    const scan = wrapper.get('a.scan-card').attributes('href')!
    expect(scan).toContain('api_key=' + key)
    expect(scan).toContain('link_state=verified')
    // Documents-only choices and search text stay behind.
    expect(scan).not.toContain('unassigned')
    expect(scan).not.toContain('q=')
    await wrapper.get('.document-link').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      library: ['a'], document: 'a-shared', api_key: [key], link_state: ['verified'],
    })
  })
  it('loads at most four previews and paginates document results without following page cursors', async () => {
    api.documents.mockImplementation(({ query }) =>
      Promise.resolve(
        query.cursor
          ? response([doc('b'), doc('c', 'empty', 'Empty')])
          : response([doc('a'), doc('b')], 3, 'documents-next'),
      ),
    )
    api.pages.mockImplementation(({ query }) =>
      Promise.resolve(
        lib(query) === 'c'
          ? response([])
          : response(
              Array.from({ length: 4 }, (_, i) => page(lib(query), `${lib(query)}-${i}`)),
              20,
              'unused-next',
            ),
      ),
    )
    const { wrapper } = await render()
    expect(wrapper.findAll('.scan-card')).toHaveLength(8)
    expect(wrapper.text()).toContain('20 registered pages')
    expect(wrapper.findAll('.more-pages').map((node) => node.text())).toEqual(['+16', '+16'])
    expect(wrapper.get('.more-pages').attributes('href')).toBe('/scans?document=a-shared')
    expect(wrapper.text()).not.toContain('Showing 4 of')
    expect(wrapper.find('button[aria-label^="Load more pages"]').exists()).toBe(false)
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Load more documents')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.findAll('article')).toHaveLength(3)
    expect(wrapper.text()).toContain('No pages have been registered for this document yet.')
    expect(api.pages.mock.calls.every(([arg]) => !arg.query.cursor)).toBe(true)
    expect(api.documents.mock.calls[1]![0].query.cursor).toBe('documents-next')
  })
  it('retries a failed group without hiding the other document', async () => {
    let resolvePages: (value: unknown) => void = () => {}
    api.pages.mockImplementation(({ query }) =>
      lib(query) === 'a'
        ? new Promise((resolve) => {
            resolvePages = resolve
          })
        : Promise.reject(new Error('Unavailable')),
    )
    const { wrapper } = await render()
    expect(wrapper.findAll('h2')).toHaveLength(2)
    expect(wrapper.text()).toContain('Could not load pages for this document.')
    resolvePages(response([page('a', 'a-1')]))
    await flushPromises()
    expect(wrapper.findAll('a.scan-card')).toHaveLength(1)
    api.pages.mockResolvedValue(response([]))
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Retry pages')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.findAll('h2')).toHaveLength(2)
  })
  it('retains document results after a next-page error and retries that cursor', async () => {
    let fail = true
    api.documents.mockImplementation(({ query }) =>
      !query.cursor
        ? Promise.resolve(response([doc('a')], 2, 'docs-next'))
        : fail
          ? Promise.reject(new Error('Next document unavailable'))
          : Promise.resolve(response([doc('b')], 2)),
    )
    const { wrapper } = await render()
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Load more documents')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.findAll('article')).toHaveLength(1)
    expect(wrapper.text()).toContain('Could not load documents.')
    fail = false
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Retry documents')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.findAll('article')).toHaveLength(2)
    expect(api.documents.mock.calls.map(([arg]) => arg.query.cursor)).toEqual([
      null,
      'docs-next',
      'docs-next',
    ])
  })
  it.each(['items', 'table'])('restores combined URL filters, tags and clear/history behavior in %s', async (view) => {
    const { wrapper, router } = await render(
      `/documents?q=Ada&library=a&library=b&link_state=verified&unassigned=no&touched_from=2026-01-01T00:00:00Z&touched_by=${user}&api_key=${key}${view === 'table' ? '&view=table' : ''}`,
    )
    expect(api.documents).not.toHaveBeenCalled()
    expect(api.search).toHaveBeenLastCalledWith(
      expect.objectContaining({
        query: expect.objectContaining({
          'query.text': ['Ada'],
          'filter.library': ['a', 'b'],
          'filter.entity_link_state': ['verified'],
          'filter.has_unassigned_faces': false,
          'filter.last_touched_by_user_id': [user],
          'filter.last_touched_by_api_key_id': [key],
          'filter.last_touched_from': '2026-01-01T00:00:00.000Z',
          cursor: null,
          return_total_count: true,
        }),
      }),
    )
    // Previews: this document's pages matching the same shared criteria; the
    // Documents-only unassigned-faces choice does not restrict pages.
    if (view === 'table') expect(api.pages).not.toHaveBeenCalled()
    else expect(api.pages.mock.calls[0]![0].query).toEqual({
      'filter.document_source_id': ['a-shared'],
      'filter.entity_link_state': ['verified'],
      'filter.last_touched_by_user_id': [user],
      'filter.last_touched_by_api_key_id': [key],
      'filter.last_touched_from': '2026-01-01T00:00:00.000Z',
      sort: 'page_id',
      limit: 4,
      return_total_count: true,
      cursor: null,
    })
    await wrapper.get('button[aria-label="Remove Library: a"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.library).toEqual(['b'])
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Clear all filters')!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'Ada', ...(view === 'table' && { view }) })
    await wrapper.get('input[aria-label="Search documents"]').setValue('  ')
    await flushPromises()
    expect(api.documents).toHaveBeenCalled()
    router.back()
    await flushPromises()
    expect(
      wrapper.get<HTMLInputElement>('input[aria-label="Search documents"]').element.value,
    ).toBe('Ada')
  })
  it.each(['items', 'table'])('shows no matches and suppresses invalid dates in %s', async (view) => {
    api.documents.mockResolvedValue(response([]))
    const { wrapper, router } = await render(`/documents?library=missing&view=${view}`)
    expect(wrapper.text()).toContain('No documents match your search and filters.')
    const calls = api.documents.mock.calls.length
    await router.push(
      '/documents?touched_from=2026-02-01T00:00:00Z&touched_to=2026-01-01T00:00:00Z',
    )
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('before or equal')
    expect(api.documents.mock.calls.length).toBe(calls)
  })
  it.each(['items', 'table'])('keeps active tags accessible with mobile filters collapsed in %s', async (view) => {
    desktop.value = false
    const { wrapper, router } = await render(`/documents?q=Ada&library=a${view === 'table' ? '&view=table' : ''}`)
    expect(wrapper.get('button[aria-label="Show filters"]').attributes('aria-expanded')).toBe(
      'false',
    )
    expect(wrapper.find('button[aria-label="Libraries"]').exists()).toBe(false)
    const panel = wrapper.get('.search-filter-panel')
    const active = wrapper.get('.active-filters')
    expect(panel.element.contains(active.element)).toBe(false)
    expect(active.find('[data-slot="badge"]').exists()).toBe(true)
    await wrapper.get('button[aria-label="Show filters"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('button[aria-label="Libraries"]').exists()).toBe(true)
    await wrapper.get('button[aria-label="Hide filters"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.active-filters').exists()).toBe(true)
    await active.get('button[aria-label="Remove Library: a"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'Ada', ...(view === 'table' && { view }) })
    expect(wrapper.find('.active-filters').exists()).toBe(false)
  })
  it('keeps scan result envelopes separate from raw page list cache entries', async () => {
    const { queryClient, wrapper } = await render()
    let search: ReturnType<typeof useDocumentSearch> | undefined
    const harness = mount(
      defineComponent({
        setup() {
          search = useDocumentSearch('', 'all', 12, {
            'filter.library': ['a'],
            'filter.document_id': ['shared'],
          })
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
    )
    cleanups.push(() => harness.unmount())
    await flushPromises()
    expect(search!.resultCount.value).toBe(1)
    expect(search!.cards.value[0]?.library).toBe('a')
    expect(wrapper.findAll('h2')).toHaveLength(2)
  })
})

describe('document presentation navigation', () => {
  it('switches presentation without changing search, filters, sort or the result query', async () => {
    const { wrapper, router } = await render(
      '/documents?q=Album&library=a&sort=document_id&dir=desc&view=table',
    )
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(api.pages).not.toHaveBeenCalled()
    const firstParams = api.search.mock.calls[0]![0].query
    await wrapper.get('[aria-label="Items view"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.document-row')).toHaveLength(1)
    expect(router.currentRoute.value.query).toEqual({
      q: 'Album',
      library: 'a',
      sort: 'document_id',
      dir: 'desc',
    })
    await wrapper.get('[aria-label="Table view"]').trigger('click')
    await flushPromises()
    expect(api.search).toHaveBeenCalledTimes(1)
    expect(api.search.mock.calls[0]![0].query).toEqual(firstParams)
    router.back()
    await flushPromises()
    expect(wrapper.find('table').exists()).toBe(false)
    router.forward()
    await flushPromises()
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
  })
})
