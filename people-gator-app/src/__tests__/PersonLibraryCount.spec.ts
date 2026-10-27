import { mount, flushPromises } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { expect, it, vi } from 'vitest'
import PersonLibraryCount from '@/components/custom/PersonLibraryCount.vue'
const api = vi.hoisted(() => ({ pages: vi.fn() }))
vi.mock('@/client', () => ({ listPagesRouteApiV1PagesGet: api.pages }))
it('counts distinct libraries from every linked page, including mention-only libraries', async () => {
  api.pages
    .mockResolvedValueOnce({
      data: { items: [{ library: 'faces' }, { library: 'faces' }], cursor: 'next' },
    })
    .mockResolvedValueOnce({ data: { items: [{ library: 'mentions-only' }], cursor: null } })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(PersonLibraryCount, {
    props: { personId: 'person' },
    global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
  })
  await flushPromises()
  expect(wrapper.get('dd').text()).toBe('2')
  expect(api.pages.mock.calls[1]![0].query).toEqual({
    'filter.entity_id': ['person'],
    limit: 100,
    cursor: 'next',
  })
  wrapper.unmount()
  client.clear()
})
