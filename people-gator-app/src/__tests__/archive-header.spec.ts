import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expect, it, vi } from 'vitest'
import TopBar from '@/components/custom/TopBar.vue'

const lookup = vi.hoisted(() => vi.fn())
vi.mock('@/client', async (original) => ({
  ...(await original<object>()),
  lookupPageRouteApiV1PagesLookupGet: lookup,
}))

it('uses the API page URL and clears it while navigating or when the source is unavailable', async () => {
  let resolve!: (value: unknown) => void
  lookup.mockResolvedValueOnce({ data: { url: 'https://archive.example/canonical-page-one' } })
  lookup.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
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
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(TopBar, {
    global: { plugins: [router, [VueQueryPlugin, { queryClient: client }]] },
  })
  await flushPromises()
  expect(wrapper.get('a[target="_blank"]').attributes('href')).toBe(
    'https://archive.example/canonical-page-one',
  )
  await router.push('/other-library/other-document/two')
  await flushPromises()
  expect(wrapper.find('a[target="_blank"]').exists()).toBe(false)
  expect(lookup.mock.lastCall?.[0].query).toEqual({
    library: 'other-library',
    document_id: 'other-document',
    page_id: 'two',
  })
  resolve({ data: { url: 'https://archive.example/canonical-page-two' } })
  await flushPromises()
  expect(wrapper.get('a[target="_blank"]').attributes('href')).toBe(
    'https://archive.example/canonical-page-two',
  )
  lookup.mockRejectedValueOnce(new Error('Source unavailable'))
  await router.push('/lib/doc/missing')
  await flushPromises()
  expect(wrapper.find('a[target="_blank"]').exists()).toBe(false)
  wrapper.unmount()
  client.clear()
})
