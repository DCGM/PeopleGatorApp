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

import DocumentSearchView from '@/views/DocumentSearchView.vue'
import { readEvidenceFilters } from '@/viewmodels/evidence-filters'

describe('opening a scan from search', () => {
  it.each<LocationQuery>([
    {},
    {
      evidence_source: '00000000-0000-4000-8000-000000000002',
      evidence_document: '00000000-0000-4000-8000-000000000003',
      evidence_key: '00000000-0000-4000-8000-000000000004',
      evidence_user: '00000000-0000-4000-8000-000000000005',
      evidence_from: '2026-01-01T00:00:00Z',
      link_state: 'manual',
    },
  ])('preserves selected evidence without inventing a page filter: %j', async (query) => {
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
        plugins: [router],
        stubs: { DocumentSearchBar: true, DocumentCard: true },
      },
    })
    try {
      await wrapper.get('section a').trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.name).toBe('document-page')
      expect(router.currentRoute.value.params.pageId).toBe('page')
      expect(readEvidenceFilters(router.currentRoute.value.query)).toEqual(
        readEvidenceFilters(query),
      )
    } finally {
      wrapper.unmount()
    }
  })
})
