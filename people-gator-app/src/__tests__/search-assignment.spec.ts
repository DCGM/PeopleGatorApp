import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchEntities: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchEntitySearch: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchFaces: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchTextMentions: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchPages: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchPageSearch: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchPage: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchPageImage: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  fetchSources: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))

vi.mock('@/query/entities', () => ({ fetchEntities: mocks.fetchEntities }))
vi.mock('@/query/faces', () => ({ fetchFaces: mocks.fetchFaces }))
vi.mock('@/query/text-mentions', () => ({ fetchTextMentions: mocks.fetchTextMentions }))
vi.mock('@/query/search', () => ({
  fetchEntitySearch: mocks.fetchEntitySearch,
  fetchPageSearch: mocks.fetchPageSearch,
}))
vi.mock('@/query/media', () => ({
  fetchPage: mocks.fetchPage,
  fetchPageImage: mocks.fetchPageImage,
  fetchPages: mocks.fetchPages,
  fetchSources: mocks.fetchSources,
}))

import { assignmentType, normalizeAssignmentFilter } from '@/query/assignment'
import { useDocumentSearch } from '@/query/document-search'
import { usePeopleSearch } from '@/query/people-search'

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
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.fetchEntitySearch.mockResolvedValue({
      items: [],
      total_count: 0,
      limit: 13,
      after_id: null,
    })
    mocks.fetchPageSearch.mockResolvedValue({
      items: [],
      total_count: 0,
      limit: 13,
      after_id: null,
    })
    mocks.fetchPages.mockResolvedValue({
      items: [],
      total_count: 0,
      limit: 13,
      after_id: null,
    })
  })

  it('normalizes route values and maps UI values to API values', () => {
    expect(normalizeAssignmentFilter('faces')).toBe('faces')
    expect(normalizeAssignmentFilter('mentions')).toBe('mentions')
    expect(normalizeAssignmentFilter('names')).toBe('mentions')
    expect(normalizeAssignmentFilter('invalid')).toBe('all')
    expect(assignmentType('faces')).toBe('face')
    expect(assignmentType('mentions')).toBe('text_mention')
    expect(assignmentType('all')).toBeUndefined()
  })

  it('sends the assigned-face filter when searching people', async () => {
    const wrapper = mountQuery(() => {
      usePeopleSearch(ref('Ada'), ref('faces'), 12)
    })
    await flushPromises()

    expect(mocks.fetchEntitySearch).toHaveBeenCalledWith(
      { q: ['Ada'], assignment: 'face', limit: 13 },
      expect.any(AbortSignal),
    )
    wrapper.unmount()
  })

  it('sends the assigned-mention filter when searching pages', async () => {
    const wrapper = mountQuery(() => {
      useDocumentSearch(ref('Ada'), ref('mentions'), 12)
    })
    await flushPromises()

    expect(mocks.fetchPageSearch).toHaveBeenCalledWith(
      { q: 'Ada', assignment: 'text_mention', limit: 13 },
      expect.any(AbortSignal),
    )
    wrapper.unmount()
  })

  it('uses the filtered page listing when the search term is empty', async () => {
    const wrapper = mountQuery(() => {
      useDocumentSearch(ref(''), ref('faces'), 12)
    })
    await flushPromises()

    expect(mocks.fetchPages).toHaveBeenCalledWith(
      { assignment: 'face', limit: 13 },
      expect.any(AbortSignal),
    )
    expect(mocks.fetchSources).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
