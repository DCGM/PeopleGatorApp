import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { computed } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ list: vi.fn(), search: vi.fn() }))
vi.mock('@/query/entities', () => ({ fetchEntities: api.list }))
vi.mock('@/query/media', () => ({ fetchPages: api.list, fetchDocuments: api.list }))
vi.mock('@/query/faces', () => ({ fetchFaces: vi.fn() }))
vi.mock('@/query/text-mentions', () => ({ fetchTextMentions: vi.fn() }))
vi.mock('@/client', () => ({
  searchEntitiesGetApiV1SearchEntitiesGet: api.search,
  searchPagesGetApiV1SearchPagesGet: api.search,
  searchDocumentsGetApiV1SearchDocumentsGet: api.search,
}))
vi.mock('@/query/people-filter-options', () => ({
  useSourceLabels: () => ({ labels: computed(() => ({})) }),
}))
vi.mock('@/viewmodels/page-cards', () => ({
  usePageCards: (pages: { value: Array<{ source_id: string }> }) =>
    computed(() => pages.value.map((page) => ({ sourceId: page.source_id }))),
}))
import PeopleSearchView from '@/views/PeopleSearchView.vue'
import DocumentSearchView from '@/views/DocumentSearchView.vue'
import DocumentListView from '@/views/DocumentListView.vue'

let endTop: number
let minimumHeightLayout: boolean
let intersection: () => void
let layoutChanged: () => void
let frames: Map<number, FrameRequestCallback>
let frameId = 0
const disconnectIntersection = vi.fn()
const disconnectResize = vi.fn()
const cleanups: Array<() => void> = []
const record = (id: string) => ({
  entity_id: id,
  source_id: id,
  name: id,
  library: 'test',
  documentId: id,
  entity_link_stats: { faces: { total: 0 }, mentions: { total: 0 } },
})
const batch = (ids: string[], cursor: string | null = null) => ({
  items: ids.map(record),
  cursor,
  total_count: 3,
  limit: 12,
})
async function settle() {
  await flushPromises()
  const callbacks = [...frames.values()]
  frames.clear()
  for (const callback of callbacks) callback(0)
  await flushPromises()
}
beforeEach(() => {
  vi.clearAllMocks()
  frames = new Map()
  endTop = 1500
  minimumHeightLayout = false
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement,
  ) {
    const sentinel = this.getAttribute('aria-hidden') === 'true'
    // Model a short list inside a section starting at 200px with min-height:
    // 100dvh. A sibling sentinel follows the section's minimum height, while a
    // child follows the cards, before the section's remaining blank space.
    const top = sentinel
      ? minimumHeightLayout && !this.closest('.stable-search-results')
        ? Math.max(endTop, 200 + document.documentElement.clientHeight)
        : endTop
      : 0
    return {
      top,
      bottom: top + 1,
      left: 0,
      right: 900,
      width: 900,
      height: 1,
      x: 0,
      y: top,
      toJSON() {},
    }
  })
  vi.spyOn(document.documentElement, 'clientHeight', 'get').mockReturnValue(900)
  vi.spyOn(document.documentElement, 'clientWidth', 'get').mockReturnValue(1000)
  vi.stubGlobal('requestAnimationFrame', (fn: FrameRequestCallback) => {
    frames.set(++frameId, fn)
    return frameId
  })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id))
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      constructor(callback: () => void) {
        intersection = callback
      }
      observe() {}
      disconnect = disconnectIntersection
    },
  )
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback: () => void) {
        layoutChanged = callback
      }
      observe() {}
      disconnect = disconnectResize
    },
  )
  api.list.mockImplementation(async ({ cursor }) =>
    cursor ? batch(['second']) : batch(['first'], 'next'),
  )
  api.search.mockImplementation(async ({ query }) => ({ data: await api.list(query) }))
})
afterEach(() => {
  cleanups.splice(0).forEach((cleanup) => cleanup())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

const screens = [
  { name: 'people', view: PeopleSearchView, sort: 'name' },
  { name: 'scans', view: DocumentSearchView, sort: 'page_id' },
  { name: 'documents', view: DocumentListView, sort: 'name' },
]
for (const screen of screens)
  describe(`automatic ${screen.name} pagination`, () => {
    async function render(query = '') {
      const router = createRouter({
        history: createMemoryHistory(),
        routes: [
          { path: '/', component: screen.view },
          { path: '/person/:personId', name: 'person-detail', component: { template: '<div />' } },
          {
            path: '/page/:libraryId?/:documentId?/:pageId?',
            name: 'document-page',
            component: { template: '<div />' },
          },
        ],
      })
      await router.push('/' + query)
      const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
      const wrapper = mount(screen.view, {
        attachTo: document.body,
        global: {
          plugins: [router, [VueQueryPlugin, { queryClient: client }]],
          stubs: {
            PeopleSearchBar: true,
            DocumentSearchBar: true,
            DocumentListSearchBar: true,
            PeopleCard: { props: ['name'], template: '<span class="result">{{ name }}</span>' },
            DocumentCard: { props: ['library'], template: '<span class="result">scan</span>' },
            DocumentPageGroup: {
              props: ['document'],
              template: '<span class="result">{{ document.name }}</span>',
            },
          },
        },
      })
      cleanups.push(() => {
        wrapper.unmount()
        client.clear()
      })
      await settle()
      return { wrapper, router, client }
    }
    it.each(['', '?q=Pagination'])(
      'loads at the visible end in browse/search (%s), preserving results and cursor order',
      async (query) => {
        const { wrapper } = await render(query)
        expect(wrapper.findAll('.result')).toHaveLength(1)
        expect(api.list).toHaveBeenCalledTimes(1)
        endTop = 700
        intersection()
        window.dispatchEvent(new Event('scroll'))
        await settle()
        expect(wrapper.findAll('.result')).toHaveLength(2)
        expect(api.list.mock.calls.map(([params]) => params.cursor)).toEqual([null, 'next'])
        intersection()
        layoutChanged()
        await settle()
        expect(api.list).toHaveBeenCalledTimes(2)
        expect(wrapper.text()).not.toContain('Load more')
        if (query)
          expect(
            api.search.mock.calls.every(([arg]) => arg.query['query.text'][0] === 'Pagination'),
          ).toBe(true)
      },
    )
    it('fills spare space through successive batches without another intersection or scroll', async () => {
      endTop = 500
      api.list.mockImplementation(async ({ cursor }) =>
        cursor === 'last'
          ? batch(['third'])
          : cursor
            ? batch(['second'], 'last')
            : batch(['first'], 'next'),
      )
      const { wrapper } = await render()
      await settle()
      await settle()
      expect(wrapper.findAll('.result')).toHaveLength(3)
      expect(api.list.mock.calls.map(([p]) => p.cursor)).toEqual([null, 'next', 'last'])
    })
    if (screen.name !== 'documents')
      it.each(['', '?q=Pagination'])(
        'fills spare space before the mobile results section minimum height (%s)',
        async (query) => {
          minimumHeightLayout = true
          endTop = 500
          const { wrapper } = await render(query)
          await settle()
          expect(wrapper.findAll('.result')).toHaveLength(2)
          expect(api.list.mock.calls.map(([params]) => params.cursor)).toEqual([null, 'next'])
        },
      )
    it('rechecks resize/layout and stops once appended content fills the viewport', async () => {
      const { wrapper } = await render()
      api.list.mockImplementation(async () => {
        endTop = 1600
        return batch(['second'], 'last')
      })
      endTop = 500
      window.dispatchEvent(new Event('resize'))
      await settle()
      await settle()
      expect(wrapper.findAll('.result')).toHaveLength(2)
      expect(api.list).toHaveBeenCalledTimes(2)
      endTop = 600
      api.list.mockResolvedValue(batch(['third']))
      layoutChanged()
      await settle()
      expect(wrapper.findAll('.result')).toHaveLength(3)
    })
    it('serializes delayed requests, guards the manual button, and cleans up on navigation', async () => {
      const { wrapper } = await render()
      let complete!: (value: ReturnType<typeof batch>) => void
      api.list.mockImplementation(
        () =>
          new Promise((resolve) => {
            complete = resolve
          }),
      )
      endTop = 500
      intersection()
      await settle()
      intersection()
      layoutChanged()
      window.dispatchEvent(new Event('resize'))
      await settle()
      expect(api.list).toHaveBeenCalledTimes(2)
      expect(wrapper.get('button').attributes('disabled')).toBeDefined()
      wrapper.unmount()
      complete(batch(['second'], 'last'))
      window.dispatchEvent(new Event('scroll'))
      intersection()
      await settle()
      expect(api.list).toHaveBeenCalledTimes(2)
      expect(disconnectIntersection).toHaveBeenCalled()
      expect(disconnectResize).toHaveBeenCalled()
      expect(frames.size).toBe(0)
    })
    it('pauses after failure, keeps results and permits manual retry with the same cursor', async () => {
      const { wrapper } = await render()
      api.list.mockRejectedValue(new Error('Unavailable'))
      endTop = 500
      intersection()
      await settle()
      for (let i = 0; i < 3; i++) {
        intersection()
        layoutChanged()
        await settle()
      }
      expect(api.list).toHaveBeenCalledTimes(2)
      expect(wrapper.findAll('.result')).toHaveLength(1)
      api.list.mockResolvedValue(batch(['second']))
      await wrapper.get('button').trigger('click')
      await settle()
      expect(wrapper.findAll('.result')).toHaveLength(2)
      expect(api.list.mock.calls.map(([p]) => p.cursor)).toEqual([null, 'next', 'next'])
    })
    it('restarts on changed search/filter/sort and never appends a stale delayed batch', async () => {
      const { wrapper, router } = await render()
      let complete!: (value: ReturnType<typeof batch>) => void
      api.list.mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            complete = resolve
          }),
      )
      endTop = 500
      intersection()
      await settle()
      api.list.mockImplementation(async ({ cursor }) =>
        cursor ? batch(['fresh-second']) : batch(['fresh-first'], 'fresh-next'),
      )
      await router.push(`/?q=Fresh&library=test&sort=${screen.sort}&dir=desc`)
      await settle()
      complete(batch(['stale'], 'stale-next'))
      await settle()
      await settle()
      expect(wrapper.findAll('.result')).toHaveLength(2)
      expect(wrapper.text()).not.toContain('stale')
      const last = api.list.mock.calls[api.list.mock.calls.length - 1]![0]
      expect(last.cursor).toBe('fresh-next')
      expect(last['filter.library']).toEqual(['test'])
      expect(last.sort).toBe(screen.sort)
      expect(last.sort_direction).toBe('desc')
    })
    it('uses the clipping scroll container and remains usable without observers', async () => {
      vi.stubGlobal('IntersectionObserver', undefined)
      vi.stubGlobal('ResizeObserver', undefined)
      const { wrapper } = await render()
      wrapper.element.style.overflowY = 'auto'
      vi.spyOn(wrapper.element, 'clientHeight', 'get').mockReturnValue(400)
      endTop = 500
      window.dispatchEvent(new Event('resize'))
      await settle()
      expect(api.list).toHaveBeenCalledTimes(1)
      endTop = 300
      wrapper.element.dispatchEvent(new Event('scroll'))
      await settle()
      expect(wrapper.findAll('.result')).toHaveLength(2)
    })
    it('keeps the manual control available and guards background refetches', async () => {
      const { wrapper, client } = await render()
      let complete!: (value: ReturnType<typeof batch>) => void
      api.list.mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            complete = resolve
          }),
      )
      const refetch = client.refetchQueries()
      await settle()
      endTop = 500
      intersection()
      await settle()
      expect(api.list).toHaveBeenCalledTimes(2)
      expect(wrapper.get('button').attributes('disabled')).toBeDefined()
      complete(batch(['first'], 'next'))
      await refetch
      endTop = 1500
      await settle()
      expect(api.list).toHaveBeenCalledTimes(2)
      await wrapper.get('button').trigger('click')
      await settle()
      expect(wrapper.findAll('.result')).toHaveLength(2)
    })
    it('does not load empty results or a disabled configuration', async () => {
      endTop = 500
      api.list.mockResolvedValue(batch([]))
      const { wrapper, router } = await render()
      expect(wrapper.findAll('.result')).toHaveLength(0)
      await settle()
      expect(api.list).toHaveBeenCalledTimes(1)
      await router.push('/?touched_from=2026-02-01T00:00:00Z&touched_to=2026-01-01T00:00:00Z')
      window.dispatchEvent(new Event('resize'))
      await settle()
      expect(api.list).toHaveBeenCalledTimes(1)
    })
  })
