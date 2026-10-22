import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { createMemoryHistory, createRouter, type LocationQuery } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/viewmodels/document-search', () => ({
  useDocumentSearch: () => ({
    cards: ref([
      {
        sourceId: '00000000-0000-4000-8000-000000000001',
        library: 'preview-mzk',
        documentId: 'document',
        pageId: 'page',
        names: [],
      },
    ]),
    error: ref(null),
    hasNextPage: ref(false),
    isFetchingNextPage: ref(false),
    isLoading: ref(false),
    loadMore: vi.fn(),
    resultCount: ref(1),
  }),
}))

const media = vi.hoisted(() => ({ fetchDocuments: vi.fn() }))
vi.mock('@/query/media', () => media)
vi.mock('@/query/search/pages', () => ({ fetchPageSearch: vi.fn() }))
const registered = '00000000-0000-4000-8000-000000000003'
media.fetchDocuments.mockImplementation(async ({ 'filter.source_id': ids = [] }) => ({
  items: ids.includes(registered)
    ? [{ source_id: registered, library: 'preview-mzk', document_id: 'archive', name: 'Ledger' }]
    : [],
}))
import DocumentSearchView from '@/views/DocumentSearchView.vue'
import { readSharedFilters } from '@/viewmodels/shared-filters'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

describe('opening a scan from search', () => {
  it.each<LocationQuery>([
    {},
    {
      page: '00000000-0000-4000-8000-000000000002',
      document: registered,
      api_key: '00000000-0000-4000-8000-000000000004',
      touched_by: '00000000-0000-4000-8000-000000000005',
      touched_from: '2026-01-01T00:00:00Z',
      link_state: 'manual',
    },
  ])('preserves the shared configuration without inventing a page filter: %j', async (query) => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/scans', name: 'document-search', component: DocumentSearchView },
        {
          path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
          name: 'document-page',
          component: defineComponent(() => () => null),
        },
      ],
    })
    await router.push({ path: '/scans', query })
    const wrapper = mount(DocumentSearchView, {
      global: {
        plugins: [router, [VueQueryPlugin, { queryClient: new QueryClient() }]],
        stubs: { DocumentSearchBar: true, DocumentCard: true },
      },
    })
    try {
      await wrapper.get('section a').trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.name).toBe('document-page')
      expect(router.currentRoute.value.params.pageId).toBe('page')
      expect(readSharedFilters(router.currentRoute.value.query)).toEqual(
        readSharedFilters(query),
      )
    } finally {
      wrapper.unmount()
    }
  })
})
