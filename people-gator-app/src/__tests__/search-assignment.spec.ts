import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchEntities: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  searchEntities: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchFaces: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchTextMentions: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchPages: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  searchPages: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchPage: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchPageImage: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))

vi.mock('@/query/entities', () => ({ fetchEntities: mocks.fetchEntities }))
vi.mock('@/query/faces', () => ({ fetchFaces: mocks.fetchFaces }))
vi.mock('@/query/text-mentions', () => ({ fetchTextMentions: mocks.fetchTextMentions }))
vi.mock('@/client', () => ({
  searchEntitiesGetApiV1SearchEntitiesGet: mocks.searchEntities,
  searchPagesGetApiV1SearchPagesGet: mocks.searchPages,
}))
vi.mock('@/query/media', () => ({
  fetchPage: mocks.fetchPage,
  fetchPageImage: mocks.fetchPageImage,
  fetchPages: mocks.fetchPages,
}))

import { useEntitySearchQuery } from '@/query/search'
import {
  assignmentEntityFilter,
  assignmentType,
  normalizeAssignmentFilter,
} from '@/viewmodels/assignment'
import { useDocumentSearch } from '@/viewmodels/document-search'
import { usePeopleSearch } from '@/viewmodels/people-search'

function mountQuery(setup: () => void) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const Harness = defineComponent({
    setup() {
      setup()
      return () => h('div')
    },
  })
  return mount(Harness, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
}

describe('assignment search filters', () => {
  const page = {
    source_id: 'page-1',
    source_type: 'page',
    url: 'https://example.test/page-1',
    library: 'library',
    document_id: 'document-1',
    page_id: 'page-1',
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mocks.fetchEntities.mockResolvedValue({
      items: [],
      total_count: 0,
      limit: 12,
      cursor: null,
    })
    mocks.searchEntities.mockResolvedValue({
      data: {
        items: [],
        total_count: 0,
        limit: 12,
        cursor: null,
      },
    })
    mocks.searchPages.mockResolvedValue({
      data: {
        items: [],
        total_count: 0,
        limit: 12,
        cursor: null,
      },
    })
    mocks.fetchPages.mockResolvedValue({
      items: [],
      total_count: 0,
      limit: 12,
      cursor: null,
    })
    mocks.fetchFaces.mockResolvedValue({
      items: [{ entity_id: 'person-1' }],
      total_count: 1,
      limit: 100,
      cursor: null,
    })
    mocks.fetchTextMentions.mockResolvedValue({
      items: [{ entity_id: 'person-1' }],
      total_count: 1,
      limit: 100,
      cursor: null,
    })
    mocks.fetchPage.mockResolvedValue(page)
    mocks.fetchPageImage.mockResolvedValue(new Blob())
  })

  it('normalizes route values and maps UI values to API values', () => {
    expect(normalizeAssignmentFilter('faces')).toBe('faces')
    expect(normalizeAssignmentFilter('mentions')).toBe('mentions')
    expect(normalizeAssignmentFilter('names')).toBe('mentions')
    expect(normalizeAssignmentFilter('invalid')).toBe('all')
    expect(assignmentType('faces')).toBe('face')
    expect(assignmentType('mentions')).toBe('text_mention')
    expect(assignmentType('all')).toBeUndefined()
    expect(assignmentEntityFilter('faces')).toEqual({
      hasDetections: true,
      hasMentions: undefined,
    })
    expect(assignmentEntityFilter('mentions')).toEqual({
      hasDetections: undefined,
      hasMentions: true,
    })
  })

  it('sends the assigned-face filter when searching people', async () => {
    const wrapper = mountQuery(() => {
      usePeopleSearch(ref('Ada'), ref('faces'), 12)
    })
    await flushPromises()

    expect(mocks.searchEntities).toHaveBeenCalledWith({
      query: {
        'query.text': ['Ada'],
        'filter.has_detections': true,
        'filter.has_mentions': undefined,
        limit: 12,
        return_total_count: true,
        cursor: null,
      },
      throwOnError: true,
      signal: expect.any(AbortSignal),
    })
    wrapper.unmount()
  })

  it('uses a supplied cursor as the initial entity-search cursor', async () => {
    const wrapper = mountQuery(() => {
      useEntitySearchQuery(ref({ 'query.text': ['Ada'], limit: 12, cursor: 'entity-start' }))
    })
    await flushPromises()

    expect(mocks.searchEntities).toHaveBeenCalledWith({
      query: { 'query.text': ['Ada'], limit: 12, cursor: 'entity-start' },
      throwOnError: true,
      signal: expect.any(AbortSignal),
    })
    wrapper.unmount()
  })

  it('uses the returned cursor for the next people-search page', async () => {
    mocks.searchEntities
      .mockResolvedValueOnce({
        data: {
          items: [],
          total_count: 2,
          limit: 12,
          cursor: 'entity-1',
        },
      })
      .mockResolvedValueOnce({
        data: {
          items: [],
          total_count: 2,
          limit: 12,
          cursor: null,
        },
      })

    let search: ReturnType<typeof usePeopleSearch> | undefined
    const wrapper = mountQuery(() => {
      search = usePeopleSearch(ref('Ada'), ref('all'), 12)
    })
    await flushPromises()
    await search?.loadMore()

    expect(mocks.searchEntities).toHaveBeenNthCalledWith(2, {
      query: {
        'query.text': ['Ada'],
        'filter.has_detections': undefined,
        'filter.has_mentions': undefined,
        limit: 12,
        return_total_count: true,
        cursor: 'entity-1',
      },
      throwOnError: true,
      signal: expect.any(AbortSignal),
    })
    wrapper.unmount()
  })

  it('uses cursors while browsing people without a search term', async () => {
    mocks.fetchEntities
      .mockResolvedValueOnce({
        items: [],
        total_count: 2,
        limit: 12,
        cursor: 'entity-1',
      })
      .mockResolvedValueOnce({
        items: [],
        total_count: 2,
        limit: 12,
        cursor: null,
      })

    let search: ReturnType<typeof usePeopleSearch> | undefined
    const wrapper = mountQuery(() => {
      search = usePeopleSearch(ref(''), ref('faces'), 12)
    })
    await flushPromises()
    await search?.loadMore()

    expect(mocks.fetchEntities).toHaveBeenNthCalledWith(
      1,
      {
        'filter.has_detections': true,
        'filter.has_mentions': undefined,
        limit: 12,
        return_total_count: true,
        cursor: null,
      },
      expect.any(AbortSignal),
    )
    expect(mocks.fetchEntities).toHaveBeenNthCalledWith(
      2,
      {
        'filter.has_detections': true,
        'filter.has_mentions': undefined,
        limit: 12,
        return_total_count: true,
        cursor: 'entity-1',
      },
      expect.any(AbortSignal),
    )
    wrapper.unmount()
  })

  it('keeps only pages with assigned mentions when searching', async () => {
    mocks.searchPages.mockResolvedValue({
      data: { items: [page], total_count: 1, limit: 12, cursor: null },
    })
    const wrapper = mountQuery(() => {
      useDocumentSearch(ref('Ada'), ref('mentions'), 12)
    })
    await flushPromises()

    expect(mocks.searchPages).toHaveBeenCalledWith({
      query: {
        'query.text': ['Ada'],
        limit: 12,
        return_total_count: true,
        cursor: null,
      },
      throwOnError: true,
      signal: expect.any(AbortSignal),
    })
    expect(mocks.fetchTextMentions).toHaveBeenCalledWith(
      { 'filter.source_id': ['page-1'], limit: 100, cursor: null },
      expect.any(AbortSignal),
    )
    wrapper.unmount()
  })

  it('keeps only pages with assigned faces while browsing', async () => {
    mocks.fetchPages.mockResolvedValue({
      items: [page],
      total_count: 1,
      limit: 12,
      cursor: null,
    })
    const wrapper = mountQuery(() => {
      useDocumentSearch(ref(''), ref('faces'), 12)
    })
    await flushPromises()

    expect(mocks.fetchPages).toHaveBeenCalledWith(
      { limit: 12, return_total_count: true, cursor: null },
      expect.any(AbortSignal),
    )
    expect(mocks.fetchFaces).toHaveBeenCalledWith(
      { 'filter.source_id': ['page-1'], limit: 100, cursor: null },
      expect.any(AbortSignal),
    )
    wrapper.unmount()
  })

  it('uses the returned cursor while browsing pages', async () => {
    mocks.fetchPages
      .mockResolvedValueOnce({
        items: [],
        total_count: 2,
        limit: 12,
        cursor: 'page-1',
      })
      .mockResolvedValueOnce({
        items: [],
        total_count: 2,
        limit: 12,
        cursor: null,
      })

    let search: ReturnType<typeof useDocumentSearch> | undefined
    const wrapper = mountQuery(() => {
      search = useDocumentSearch(ref(''), ref('all'), 12)
    })
    await flushPromises()
    await search?.loadMore()

    expect(mocks.fetchPages).toHaveBeenNthCalledWith(
      1,
      { limit: 12, return_total_count: true, cursor: null },
      expect.any(AbortSignal),
    )
    expect(mocks.fetchPages).toHaveBeenNthCalledWith(
      2,
      { limit: 12, return_total_count: true, cursor: 'page-1' },
      expect.any(AbortSignal),
    )
    wrapper.unmount()
  })
})
