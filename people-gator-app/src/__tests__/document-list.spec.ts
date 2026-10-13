import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  documents: vi.fn(),
  pages: vi.fn(),
  image: vi.fn(),
  entities: vi.fn(),
  detail: vi.fn(),
}))
vi.mock('@/client', () => ({
  listDocumentsRouteApiV1DocumentsGet: api.documents,
  listPagesRouteApiV1PagesGet: api.pages,
  getPageImageByIdRouteApiV1PagesPageSourceIdImageGet: api.image,
  listEntitiesRouteApiV1EntitiesGet: api.entities,
  getPageRouteApiV1PagesPageSourceIdGet: api.detail,
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

async function render() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/documents', component: DocumentListView },
      {
        path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
        name: 'document-page',
        component: defineComponent(() => () => h('div')),
      },
    ],
  })
  await router.push('/documents')
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
  api.documents.mockResolvedValue(response([doc('a'), doc('b', 'shared', null)]))
  api.pages.mockImplementation(({ query }) =>
    Promise.resolve(
      response([page(query['filter.library'][0], `${query['filter.library'][0]}-1`)]),
    ),
  )
  api.image.mockRejectedValue(new Error('Missing thumbnail'))
  api.entities.mockResolvedValue(response([{ name: 'Ada' }, { name: 'Ada' }, { name: 'Grace' }]))
})
afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup()
})

describe('grouped documents', () => {
  it('renders flat headings and cards with separate library filters, names, and detail links', async () => {
    const { wrapper } = await render()
    expect(wrapper.findAll('h2').map((node) => node.text())).toEqual(['Album', 'Document shared'])
    const children = [...wrapper.get('.document-pages').element.children]
    expect(children.map((node) => node.tagName)).toEqual(['HEADER', 'A', 'HEADER', 'A'])
    expect(wrapper.findAll('.scan-card').map((node) => node.attributes('href'))).toEqual([
      '/libraries/a/documents/shared/pages/a-1',
      '/libraries/b/documents/shared/pages/b-1',
    ])
    expect(wrapper.text()).toContain('Ada, Grace')
    expect(wrapper.findAll('svg.lucide-file-text')).toHaveLength(2)
    expect(api.detail).not.toHaveBeenCalled()
    for (const library of ['a', 'b'])
      expect(api.pages).toHaveBeenCalledWith(
        expect.objectContaining({
          query: {
            'filter.library': [library],
            'filter.document_id': ['shared'],
            limit: 12,
            return_total_count: true,
            cursor: null,
          },
        }),
      )
    expect(documentTitle({ document_id: 'legacy', name: ' ' })).toBe('Document legacy')
  })

  it('paginates each group and the registered document list independently without duplicates', async () => {
    api.documents.mockImplementation(({ query }) =>
      Promise.resolve(
        query.cursor
          ? response([doc('b'), doc('c', 'empty', 'Empty')])
          : response([doc('a'), doc('b')], 3, 'documents-next'),
      ),
    )
    api.pages.mockImplementation(({ query }) => {
      const library = query['filter.library'][0]
      if (library === 'c') return Promise.resolve(response([]))
      return Promise.resolve(
        library === 'a'
          ? query.cursor
            ? response([page('a', 'a-1'), page('a', 'a-2')], 20)
            : response([page('a', 'a-1')], 20, 'a-next')
          : response([page('b', 'b-1')]),
      )
    })
    const { wrapper } = await render()
    expect(wrapper.text()).toContain('20 registered pages')
    const groupButton = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Load more pages')!
    await groupButton.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.scan-card').map((node) => node.attributes('href'))).toEqual([
      '/libraries/a/documents/shared/pages/a-1',
      '/libraries/a/documents/shared/pages/a-2',
      '/libraries/b/documents/shared/pages/b-1',
    ])
    expect(
      api.pages.mock.calls.filter(([arg]) => arg.query['filter.library'][0] === 'b'),
    ).toHaveLength(1)
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Load more documents')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.findAll('h2')).toHaveLength(3)
    expect(wrapper.text()).toContain('0 registered pages')
    expect(wrapper.text()).toContain('No pages have been registered for this document yet.')
    expect(api.documents.mock.calls[1]![0].query.cursor).toBe('documents-next')
    expect(api.pages.mock.calls.find(([arg]) => arg.query.cursor)?.[0].query.cursor).toBe('a-next')
  })

  it('keeps headings during loading and errors, and retries one group without blocking another', async () => {
    let resolvePages: (value: unknown) => void = () => {}
    api.pages.mockImplementation(({ query }) =>
      query['filter.library'][0] === 'a'
        ? new Promise((resolve) => {
            resolvePages = resolve
          })
        : Promise.reject(new Error('Unavailable')),
    )
    const { wrapper } = await render()
    expect(wrapper.findAll('h2')).toHaveLength(2)
    expect(wrapper.findAll('.scan-card')).toHaveLength(4)
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
    expect(wrapper.text()).toContain('No pages have been registered for this document yet.')
  })

  it('retains loaded pages when the next batch fails and retries its cursor', async () => {
    let fail = true
    api.documents.mockResolvedValue(response([doc('a')]))
    api.pages.mockImplementation(({ query }) => {
      if (!query.cursor) return Promise.resolve(response([page('a', 'a-1')], 2, 'a-next'))
      if (fail) return Promise.reject(new Error('Next page unavailable'))
      return Promise.resolve(response([page('a', 'a-2')], 2))
    })
    const { wrapper } = await render()
    await wrapper.get('button[aria-label^="Load more pages"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('h2')).toHaveLength(1)
    expect(wrapper.findAll('a.scan-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('Could not load pages for this document.')
    fail = false
    await wrapper.findAll('button').find(button => button.text() === 'Retry pages')!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('a.scan-card')).toHaveLength(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(api.pages.mock.calls.map(([arg]) => arg.query.cursor)).toEqual([
      null,
      'a-next',
      'a-next',
    ])
  })

  it('filters registered documents by route library and shows an empty list', async () => {
    const { wrapper, router } = await render()
    api.documents.mockResolvedValue(response([]))
    await router.push('/documents?library=missing')
    await flushPromises()
    expect(api.documents).toHaveBeenLastCalledWith(
      expect.objectContaining({
        query: { 'filter.library': ['missing'], limit: 12, cursor: null },
      }),
    )
    expect(wrapper.findAll('h2')).toHaveLength(0)
    expect(wrapper.text()).toContain('No documents have been registered in this library yet.')
  })

  it('keeps scan result envelopes separate from raw page list cache entries', async () => {
    const { queryClient, wrapper } = await render()
    let search: ReturnType<typeof useDocumentSearch> | undefined
    const harness = mount(
      defineComponent({
        setup() {
          search = useDocumentSearch('', 'all', 12, { library: 'a', documentId: 'shared' })
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
