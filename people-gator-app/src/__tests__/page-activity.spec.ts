import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import {
  activityDays,
  mergeActivity,
  usePageActivity,
  type PageActivityItem,
} from '@/viewmodels/page-activity'

const api = vi.hoisted(() => ({ faces: vi.fn(), mentions: vi.fn() }))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  listFacesRouteApiV1FacesGet: api.faces,
  listTextMentionsRouteApiV1TextMentionsGet: api.mentions,
}))

const item = (
  id: string,
  touchedAt: string | null,
  kind: PageActivityItem['kind'] = 'face',
): PageActivityItem => ({ id, kind, label: id, touchedAt, userId: null })

describe('page activity merge (#103)', () => {
  it('shows only records every unfinished stream has loaded past', () => {
    const faces = [item('f1', '2026-01-03T10:00:00Z'), item('f2', '2026-01-01T10:00:00Z')]
    const mentions = [item('m1', '2026-01-02T10:00:00Z', 'mention')]
    // Mentions may still hold a record between m1 and f2, so f2 waits.
    expect(
      mergeActivity(
        [
          { items: faces, done: true },
          { items: mentions, done: false },
        ],
        'desc',
      ),
    ).toEqual({ items: [faces[0], mentions[0]], limitedBy: 1 })
    expect(
      mergeActivity(
        [
          { items: faces, done: true },
          { items: mentions, done: true },
        ],
        'desc',
      ).items.map((record) => record.id),
    ).toEqual(['f1', 'm1', 'f2'])
    // A stream that has not loaded yet shows nothing rather than guessing.
    expect(
      mergeActivity(
        [
          { items: faces, done: false },
          { items: [], done: false },
        ],
        'asc',
      ),
    ).toEqual({ items: [], limitedBy: 1 })
  })

  it('keeps unknown times last in both directions and orders microseconds', () => {
    const records = [
      item('old', '2026-01-01T09:00:00Z'),
      item('unknown', null),
      item('new', '2026-01-02T09:00:00Z'),
    ]
    for (const [direction, order] of [
      ['desc', ['new', 'old', 'unknown']],
      ['asc', ['old', 'new', 'unknown']],
    ] as const) {
      const { items } = mergeActivity([{ items: records, done: true }], direction)
      expect(items.map((record) => record.id)).toEqual(order)
      const days = activityDays(items)
      expect(days).toHaveLength(3)
      expect(days[2]).toMatchObject({ key: '' })
    }
    // The API orders below the millisecond; the merge must agree.
    const close = [
      item('a', '2026-01-01T09:00:00.000100+00:00'),
      item('b', '2026-01-01T09:00:00.000900+00:00'),
    ]
    expect(
      mergeActivity([{ items: close, done: true }], 'desc').items.map((record) => record.id),
    ).toEqual(['b', 'a'])
  })

  it('pages the limiting stream by last change without duplicates', async () => {
    const face = (id: string, at: string) => ({
      detection_id: id,
      last_touched_at: at,
      identifier: id,
    })
    api.faces.mockImplementation(({ query }) =>
      Promise.resolve({
        data: query.cursor
          ? { items: [face('f2', '2026-01-01T00:00:00Z')], cursor: null, total_count: 2 }
          : { items: [face('f1', '2026-01-03T00:00:00Z')], cursor: 'next', total_count: 2 },
      }),
    )
    api.mentions.mockResolvedValue({
      data: {
        items: [{ mention_id: 'm1', name: 'Ada', last_touched_at: '2026-01-02T00:00:00Z' }],
        cursor: null,
        total_count: 1,
      },
    })
    let model!: ReturnType<typeof usePageActivity>
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(
      defineComponent({
        setup() {
          model = usePageActivity(ref('page'), 'desc')
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    await flushPromises()
    expect(api.faces.mock.calls[0]![0].query).toMatchObject({
      'filter.page_source_id': ['page'],
      sort: 'last_touched_at',
      sort_direction: 'desc',
    })
    expect(model.items.value.map((record) => record.id)).toEqual(['f1'])
    expect(model.hasNextPage.value).toBe(true)
    await model.loadMore()
    await flushPromises()
    expect(model.items.value.map((record) => record.id)).toEqual(['f1', 'm1', 'f2'])
    expect(model.hasNextPage.value).toBe(false)
    expect(model.totalCount.value).toBe(3)
    expect(api.mentions).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    client.clear()
  })
})
