import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, type LocationQuery } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const media = vi.hoisted(() => ({ fetchDocuments: vi.fn() }))
vi.mock('@/query/media', () => media)
import { useDocumentScopeResolution } from '@/viewmodels/document-scope'
import { useSharedFilters } from '@/viewmodels/shared-filters'

const internal = '00000000-0000-4000-8000-000000000001'
const archive = '00000000-0000-4000-8000-000000000002'
const other = '00000000-0000-4000-8000-000000000003'
async function harness(query: LocationQuery) {
  let scope!: ReturnType<typeof useDocumentScopeResolution>
  let params!: ReturnType<ReturnType<typeof useDocumentScopeResolution>['apply']>
  const component = defineComponent({
    setup() {
      scope = useDocumentScopeResolution()
      params = scope.apply(useSharedFilters().params)
      return () => h('div')
    },
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/scans', component }],
  })
  await router.push({ path: '/scans', query })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const wrapper = mount(component, {
    global: { plugins: [router, [VueQueryPlugin, { queryClient: client }]] },
  })
  await flushPromises()
  return {
    scope,
    params,
    router,
    cleanup() {
      wrapper.unmount()
      client.clear()
    },
  }
}

describe('internal document scope and archive compatibility', () => {
  beforeEach(() => media.fetchDocuments.mockReset())

  it('keeps canonical selections and resolves only legacy archives within the selected libraries', async () => {
    media.fetchDocuments.mockImplementation(async (params = {}) => ({
      items: params['filter.source_id']
        ? [{ source_id: internal, document_id: other }]
        : [{ source_id: other, document_id: archive }],
    }))
    const test = await harness({ document: [internal, archive], library: 'preview-mzk' })
    expect(media.fetchDocuments.mock.calls[1]?.[0]).toMatchObject({
      'filter.library': ['preview-mzk'],
      'filter.document_id': [archive],
    })
    expect(test.router.currentRoute.value.query.document).toEqual([internal, other])
    expect(test.params.value).toMatchObject({ 'filter.document_source_id': [internal, other] })
    expect(test.params.value).not.toHaveProperty('filter.document_id')
    test.cleanup()
  })

  it('never broadens an unresolved internal UUID into an archive predicate', async () => {
    media.fetchDocuments.mockResolvedValue({ items: [] })
    const test = await harness({ document: internal, library: 'preview-mzk' })
    expect(test.params.value).toMatchObject({ 'filter.document_source_id': [internal] })
    expect(test.params.value).not.toHaveProperty('filter.document_id')
    expect(test.scope.unregistered.value).toEqual([])
    test.cleanup()
  })

  it('supports explicit archive breadcrumbs for pages without a registered parent', async () => {
    media.fetchDocuments.mockResolvedValue({ items: [] })
    const test = await harness({ archive_document: archive, library: 'preview-mzk' })
    expect(test.params.value).toEqual({
      'filter.library': ['preview-mzk'],
      'filter.document_id': [archive],
    })
    expect(test.scope.unregistered.value).toEqual([archive])
    // No empty source-id filter reaches the API.
    expect(media.fetchDocuments).toHaveBeenCalledTimes(1)
    expect(media.fetchDocuments.mock.calls[0]?.[0]).not.toHaveProperty('filter.source_id')
    test.cleanup()
  })

  it('reports failed lookups and allows retry without dropping the selected scope', async () => {
    media.fetchDocuments
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ items: [] })
    const test = await harness({ document: internal })
    expect(test.scope.error.value).toBeTruthy()
    await test.scope.retry()
    await flushPromises()
    expect(test.scope.error.value).toBeNull()
    expect(test.params.value).toEqual({ 'filter.document_source_id': [internal] })
    test.cleanup()
  })
})
