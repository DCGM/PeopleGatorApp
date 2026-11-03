import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import PageSourceView from '@/views/PageSourceView.vue'

const api = vi.hoisted(() => ({ page: vi.fn() }))
vi.mock('@/client', () => ({ getPageRouteApiV1PagesPageSourceIdGet: api.page }))
const cleanups: (() => void)[] = []
afterEach(() => {
  cleanups.splice(0).forEach((fn) => fn())
  vi.clearAllMocks()
})
async function render() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/documents', name: 'document-list', component: { template: '<p>Documents</p>' } },
      { path: '/pages/:pageSourceId', name: 'page-source', component: PageSourceView },
      {
        path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
        name: 'document-page',
        component: { template: '<p>Page editor</p>' },
      },
    ],
  })
  await router.push('/documents')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const wrapper = mount(RouterView, {
    global: { plugins: [router, [VueQueryPlugin, { queryClient: client }]] },
  })
  cleanups.push(() => {
    wrapper.unmount()
    client.clear()
  })
  return { router, wrapper }
}
describe('first-page source navigation', () => {
  it('resolves the source UUID to archive page metadata without leaving a redirect in history', async () => {
    api.page.mockResolvedValue({
      data: {
        source_id: 'internal-source',
        library: 'archive',
        document_id: 'document-id',
        page_id: 'archive-page-id',
      },
    })
    const { router, wrapper } = await render()
    await router.push('/pages/internal-source')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('document-page')
    expect(router.currentRoute.value.params).toEqual({
      libraryId: 'archive',
      documentId: 'document-id',
      pageId: 'archive-page-id',
    })
    expect(wrapper.text()).toContain('Page editor')
    expect(api.page).toHaveBeenCalledTimes(1)
    expect(api.page).toHaveBeenCalledWith(
      expect.objectContaining({ path: { page_source_id: 'internal-source' } }),
    )
    router.back()
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('document-list')
  })
  it('keeps a failed link recoverable and retries the same source', async () => {
    api.page
      .mockRejectedValueOnce(new Error('unavailable'))
      .mockResolvedValueOnce({
        data: {
          source_id: 'source',
          library: 'archive',
          document_id: 'document-id',
          page_id: 'page-id',
        },
      })
    const { router, wrapper } = await render()
    await router.push('/pages/source')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Could not open this page.')
    expect(wrapper.get('a').attributes('href')).toBe('/documents')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('document-page')
    expect(api.page).toHaveBeenCalledTimes(2)
  })
})
