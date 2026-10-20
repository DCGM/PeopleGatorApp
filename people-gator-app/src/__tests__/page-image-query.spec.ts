import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { AxiosError, AxiosHeaders } from 'axios'
import { defineComponent, h } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  pageImage: vi.fn<() => Promise<unknown>>(),
}))
vi.mock('@/client', () => ({
  getPageImageByIdRouteApiV1PagesPageSourceIdImageGet: mocks.pageImage,
}))

import { usePageImageQuery } from '@/query/media'

function failure(status: number) {
  const config = { headers: new AxiosHeaders() }
  return new AxiosError('failed', String(status), config, undefined, {
    status, statusText: '', headers: {}, config, data: null,
  })
}

async function settle(status: number) {
  mocks.pageImage.mockReset()
  mocks.pageImage.mockRejectedValue(failure(status))
  const queryClient = new QueryClient()
  let query!: ReturnType<typeof usePageImageQuery>
  const wrapper = mount(
    defineComponent({
      setup() {
        query = usePageImageQuery('source-1', 1024)
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  )
  return { wrapper, query: () => query }
}

describe('page image query', () => {
  it('reports missing scan media at once instead of retrying a 404', async () => {
    const { wrapper, query } = await settle(404)
    await flushPromises()
    expect(query().isError.value).toBe(true)
    expect(mocks.pageImage).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('still retries transient failures', async () => {
    vi.useFakeTimers()
    try {
      const { wrapper, query } = await settle(503)
      await vi.runAllTimersAsync()
      expect(query().isError.value).toBe(true)
      expect(mocks.pageImage).toHaveBeenCalledTimes(4)
      wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })
})
