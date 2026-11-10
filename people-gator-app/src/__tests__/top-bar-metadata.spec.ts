import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, it, vi } from 'vitest'
import TopBar from '@/components/custom/TopBar.vue'
import { queryKeys } from '@/query/keys'

const api = vi.hoisted(() => ({ document: vi.fn(), page: vi.fn(), entity: vi.fn() }))
vi.mock('@/client', async (original) => ({
  ...(await original<object>()),
  lookupDocumentRouteApiV1DocumentsLookupGet: api.document,
  lookupPageRouteApiV1PagesLookupGet: api.page,
  getEntityRouteApiV1EntitiesEntityIdGet: api.entity,
}))
afterEach(() => vi.resetAllMocks())

async function setup(start = '/lib/doc/one') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/:libraryId/:documentId/:pageId',
        name: 'document-page',
        component: { template: '<div />' },
      },
      { path: '/', name: 'document-list', component: { template: '<div />' } },
      { path: '/libraries/:libraryId/documents/:documentId', name: 'document-pages', component: { template: '<div />' } },
      { path: '/documents/:documentSourceId', name: 'document-source', component: { template: '<div />' } },
      { path: '/people', name: 'people-search', component: { template: '<div />' } },
      { path: '/people/:personId', name: 'person-detail', component: { template: '<div />' } },
    ],
  })
  await router.push(start)
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
    expect(links[1]!.attributes('href')).toBe('/?library=lib')
    expect(links[2]!.attributes('href')).toBe('/libraries/lib/documents/doc?pages_view=expanded')
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

it.each([
  ['Hana Sidebar', 'Hana Sidebar'],
  ['   ', 'p1'],
  [null, 'p1'],
])('names the person breadcrumb: %s', async (name, label) => {
  api.entity.mockResolvedValue({ data: { entity_id: 'p1', name } })
  const { wrapper, labels, dispose } = await setup('/people/p1?tab=faces')
  expect(labels()).toEqual(['PeopleGator', 'People', label])
  const links = wrapper.findAll('[aria-label="Breadcrumb"] a')
  expect(links.map((a) => a.attributes('title'))).toEqual(labels())
  expect(links[1]!.attributes('href')).toBe('/people')
  expect(links[2]!.attributes('href')).toBe('/people/p1?tab=faces')
  // Phones use the logo as the home link, leaving room for the name.
  const home = wrapper.findAll('[aria-label="Breadcrumb"] li')[0]!
  expect(home.classes()).toEqual(expect.arrayContaining(['hidden', 'sm:inline-flex']))
  const separator = wrapper.find('[data-slot="breadcrumb-separator"]')
  expect(separator.classes()).toEqual(expect.arrayContaining(['hidden', 'sm:block']))
  expect(api.document).not.toHaveBeenCalled()
  expect(api.page).not.toHaveBeenCalled()
  dispose()
})

it('keeps the person breadcrumb current across renames, navigation and failures', async () => {
  api.entity.mockResolvedValueOnce({ data: { entity_id: 'p1', name: 'Hana Sidebar' } })
  const { router, client, labels, dispose } = await setup('/people/p1')
  expect(labels()[2]).toBe('Hana Sidebar')
  client.setQueryData(queryKeys.entities.detail('p1'), { entity_id: 'p1', name: 'Hana Renamed' })
  await flushPromises()
  expect(labels()[2]).toBe('Hana Renamed')

  let rejectEntity!: (error: Error) => void
  api.entity.mockImplementationOnce(
    () =>
      new Promise((_resolve, reject) => {
        rejectEntity = reject
      }),
  )
  await router.push('/people/p2')
  await flushPromises()
  expect(labels()[2]).toBe('p2')
  rejectEntity(new Error('Not found'))
  await flushPromises()
  expect(labels()[2]).toBe('p2')
  dispose()
})
