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
  api.pages.mockImplementation(() => Promise.resolve(response([page('a', 'a-1')])))
  api.image.mockRejectedValue(new Error('Missing thumbnail'))
  api.entities.mockResolvedValue(response([{ name: 'Ada' }, { name: 'Ada' }, { name: 'Grace' }]))
})
afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup()
})

describe('document table results', () => {
  it('renders document identities without legacy previews or extra page/name requests', async () => {
    const { wrapper } = await render()
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(wrapper.findAll('tbody td:first-child').map((cell) => cell.text())).toEqual([
      'Album',
      'Document shared',
    ])
    expect(wrapper.findAll('tbody a').map((link) => link.attributes('href'))).toEqual([
      '/scans?document=a-shared',
      '/scans?document=b-shared',
    ])
    expect(wrapper.get('[data-slot="input-group"] [role="status"]').text()).toBe('2 results')
    expect(api.pages).not.toHaveBeenCalled()
    expect(api.entities).not.toHaveBeenCalled()
    expect(api.detail).not.toHaveBeenCalled()
    expect(wrapper.find('.document-row').exists()).toBe(false)
    expect(documentTitle({ document_id: 'legacy', name: ' ' })).toBe('Document legacy')
  })
  it('carries shared filters into document links, leaving search and document-only settings behind', async () => {
    const { wrapper, router } = await render(
      `/documents?library=a&api_key=${key}&link_state=verified&unassigned=yes&q=Album`,
    )
    await wrapper.get('tbody a').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      library: ['a'],
      document: 'a-shared',
      api_key: [key],
      link_state: ['verified'],
    })
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
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper.text()).toContain('Could not load documents.')
    fail = false
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Retry documents')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(api.documents.mock.calls.map(([arg]) => arg.query.cursor)).toEqual([
      null,
      'docs-next',
      'docs-next',
    ])
  })
  it.each(['', 'items', 'table'])(
    'restores combined URL filters, tags and clear/history behavior in %s',
    async (view) => {
      const { wrapper, router } = await render(
        `/documents?q=Ada&library=a&library=b&link_state=verified&unassigned=no&touched_from=2026-01-01T00:00:00Z&touched_by=${user}&api_key=${key}${view ? '&view=' + view : ''}`,
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
      expect(api.pages).not.toHaveBeenCalled()
      await wrapper.get('button[aria-label="Remove Library: a"]').trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.query.library).toEqual(['b'])
      await wrapper
        .findAll('button')
        .find((button) => button.text() === 'Clear all filters')!
        .trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.query).toEqual({ q: 'Ada', ...(view && { view }) })
      await wrapper.get('input[aria-label="Search documents"]').setValue('  ')
      await flushPromises()
      expect(api.documents).toHaveBeenCalled()
      router.back()
      await flushPromises()
      expect(
        wrapper.get<HTMLInputElement>('input[aria-label="Search documents"]').element.value,
      ).toBe('Ada')
    },
  )
  it.each(['', 'items', 'table'])(
    'shows no matches and suppresses invalid dates in %s',
    async (view) => {
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
    },
  )
  it.each(['', 'items', 'table'])(
    'keeps active tags accessible with mobile filters collapsed in %s',
    async (view) => {
      desktop.value = false
      const { wrapper, router } = await render(
        `/documents?q=Ada&library=a${view ? '&view=' + view : ''}`,
      )
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
      expect(router.currentRoute.value.query).toEqual({ q: 'Ada', ...(view && { view }) })
      expect(wrapper.find('.active-filters').exists()).toBe(false)
    },
  )
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
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
  })
})

describe('table-only document navigation', () => {
  it.each(['', '&view=items', '&view=table'])(
    'uses the table on default and legacy URLs (%s)',
    async (view) => {
      const { wrapper, router } = await render(
        '/documents?q=Album&library=a&sort=document_id&dir=desc' + view,
      )
      expect(wrapper.findAll('tbody tr')).toHaveLength(1)
      expect(wrapper.find('[aria-label="Document view"]').exists()).toBe(false)
      expect(wrapper.find('[aria-label="Items view"]').exists()).toBe(false)
      expect(api.pages).not.toHaveBeenCalled()
      await router.push('/documents?library=b')
      await flushPromises()
      router.back()
      await flushPromises()
      expect(router.currentRoute.value.query.q).toBe('Album')
      expect(wrapper.findAll('tbody tr')).toHaveLength(1)
      expect(wrapper.get('[aria-label="Sort by"]').text()).toContain('Document ID')
      expect(api.search.mock.calls[0]![0].query).toMatchObject({
        sort: 'document_id',
        sort_direction: 'desc',
        'filter.library': ['a'],
      })
    },
  )
  it.each(['', '&q=Album'])(
    'header sorting shares URL/server state with the selector (%s)',
    async (search) => {
      const { wrapper, router } = await render(
        '/documents?view=table&library=a&unassigned=no' + search,
      )
      const params = () => (search ? api.search : api.documents).mock.calls.slice(-1)[0]![0].query
      const pages = wrapper.get('button[aria-label="Sort by Pages"]')
      await pages.trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.query).toMatchObject({
        view: 'table',
        library: 'a',
        unassigned: 'no',
        sort: 'page_count',
      })
      expect(params()).toMatchObject({
        sort: 'page_count',
        sort_direction: 'desc',
        cursor: null,
        'filter.library': ['a'],
        'filter.has_unassigned_faces': false,
      })
      expect(pages.element.closest('th')?.getAttribute('aria-sort')).toBe('descending')
      expect(wrapper.get('[aria-label="Sort by"]').text()).toContain('Pages · Highest first')
      await pages.trigger('click')
      await flushPromises()
      expect(params()).toMatchObject({ sort: 'page_count', sort_direction: 'asc', cursor: null })
      expect(router.currentRoute.value.query.dir).toBe('asc')
      expect(pages.element.closest('th')?.getAttribute('aria-sort')).toBe('ascending')
      expect(wrapper.get('[aria-label="Sort by"]').text()).toContain('Pages · Lowest first')
      router.back()
      await flushPromises()
      expect(pages.element.closest('th')?.getAttribute('aria-sort')).toBe('descending')
      if (search) {
        expect(params()['query.text']).toEqual(['Album'])
        await router.push('/documents?view=table&q=Album')
        await flushPromises()
        expect(wrapper.find('th[aria-sort]').exists()).toBe(false) // Relevance has no data column.
        expect(wrapper.get('[aria-label="Sort by"]').text()).toContain('Relevance')
      }
    },
  )
})
