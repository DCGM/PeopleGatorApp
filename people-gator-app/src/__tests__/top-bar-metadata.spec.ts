import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, it, vi } from 'vitest'
import TopBar from '@/components/custom/TopBar.vue'
import { queryKeys } from '@/query/keys'

const api = vi.hoisted(() => ({ document: vi.fn(), page: vi.fn() }))
vi.mock('@/client', async (original) => ({
  ...(await original<object>()),
  lookupDocumentRouteApiV1DocumentsLookupGet: api.document,
  lookupPageRouteApiV1PagesLookupGet: api.page,
}))
afterEach(() => vi.resetAllMocks())

async function setup() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/:libraryId/:documentId/:pageId',
        name: 'document-page',
        component: { template: '<div />' },
      },
      { path: '/', name: 'document-list', component: { template: '<div />' } },
      { path: '/scans', name: 'document-search', component: { template: '<div />' } },
      { path: '/people', name: 'people-search', component: { template: '<div />' } },
    ],
  })
  await router.push('/lib/doc/one')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const wrapper = mount(TopBar, {
    global: { plugins: [router, [VueQueryPlugin, { queryClient: client }]] },
  })
  await flushPromises()
  const labels = () => wrapper.findAll('[aria-label="Breadcrumb"] a').map((a) => a.text())
  const dispose = () => {
    wrapper.unmount()
    client.clear()
  }
  return { router, wrapper, client, labels, dispose }
}

it.each([
  ['Sample Chronicle', 12, 'Sample Chronicle', 'Page 12'],
  ['Sample Chronicle', null, 'Sample Chronicle', 'Page one'],
  [null, 12, 'doc', 'Page 12'],
  ['   ', 12, 'doc', 'Page 12'],
  [undefined, undefined, 'doc', 'Page one'],
])(
  'uses independent metadata fallbacks: %s / %s',
  async (name, page_number, documentLabel, pageLabel) => {
    api.document.mockResolvedValue({ data: { name } })
    api.page.mockResolvedValue({ data: { page_number, url: 'https://archive.example/page' } })
    const { wrapper, labels, dispose } = await setup()
    expect(labels()).toEqual(['PeopleGator', 'lib', documentLabel, pageLabel])
    const links = wrapper.findAll('[aria-label="Breadcrumb"] a')
    expect(links.map((a) => a.attributes('title'))).toEqual(labels())
    expect(links[1]!.attributes('href')).toBe('/scans?library=lib')
    expect(links[2]!.attributes('href')).toBe('/scans?library=lib&archive_document=doc')
    expect(links[3]!.attributes('href')).toBe('/lib/doc/one')
    expect(wrapper.get('a[target="_blank"]').attributes('href')).toBe(
      'https://archive.example/page',
    )
    dispose()
  },
)

it('clears old labels during document navigation and failed lookups, then restores history and reflects edits', async () => {
  api.document.mockResolvedValueOnce({ data: { name: 'First document' } })
  api.page.mockResolvedValueOnce({ data: { page_number: 12 } })
  const { router, client, labels, dispose } = await setup()
  expect(labels().slice(-2)).toEqual(['First document', 'Page 12'])

  let rejectDocument!: (error: Error) => void
  let resolvePage!: (result: unknown) => void
  api.document.mockImplementationOnce(
    () =>
      new Promise((_resolve, reject) => {
        rejectDocument = reject
      }),
  )
  api.page.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolvePage = resolve
      }),
  )
  await router.push('/other/second/two')
  await flushPromises()
  expect(labels().slice(-2)).toEqual(['second', 'Page two'])
  rejectDocument(new Error('Unregistered parent'))
  resolvePage({ data: { page_number: 3 } })
  await flushPromises()
  expect(labels().slice(-2)).toEqual(['second', 'Page 3'])

  // Back/Forward retains only the metadata belonging to that route.
  api.document.mockResolvedValue({ data: { name: 'First document' } })
  api.page.mockResolvedValue({ data: { page_number: 12 } })
  router.back()
  await flushPromises()
  expect(labels().slice(-2)).toEqual(['First document', 'Page 12'])
  client.setQueryData(queryKeys.pages.lookup('lib', 'doc', 'one'), { page_number: 27 })
  await flushPromises()
  expect(labels()[3]).toBe('Page 27')

  api.document.mockRejectedValue(new Error('Unavailable'))
  api.page.mockResolvedValue({ data: { page_number: 3 } })
  router.forward()
  await flushPromises()
  expect(labels().slice(-2)).toEqual(['second', 'Page 3'])
  api.page.mockRejectedValue(new Error('Unavailable'))
  await router.push('/other/second/three')
  await flushPromises()
  expect(labels().slice(-2)).toEqual(['second', 'Page three'])
  dispose()
})

it('keeps the document name while a different page loads or fails', async () => {
  api.document.mockResolvedValue({ data: { name: 'A very long catalogue title '.repeat(20) } })
  api.page.mockResolvedValueOnce({ data: { page_number: 1 } })
  const { router, wrapper, labels, dispose } = await setup()
  api.page.mockRejectedValue(new Error('Unavailable'))
  await router.push('/lib/doc/missing')
  await flushPromises()
  expect(labels()[2]).toBe('A very long catalogue title '.repeat(20).trim())
  expect(labels()[3]).toBe('Page missing')
  expect(wrapper.findAll('[aria-label="Breadcrumb"] a')[2]!.attributes('title')).toBe(labels()[2])
  dispose()
})
