import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { TextMentionResponse } from '@/client'
import { groupMentionsByPerson, useScanMentionsByPerson } from '@/viewmodels/scan-mentions'
import { readSidebarState, sidebarQuery } from '@/viewmodels/scan-sidebar'

const api = vi.hoisted(() => ({ mentions: vi.fn(), entity: vi.fn() }))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  listTextMentionsRouteApiV1TextMentionsGet: api.mentions,
  getEntityRouteApiV1EntitiesEntityIdGet: api.entity,
}))

const mention = (id: string, entity: string | null) =>
  ({ mention_id: id, entity_id: entity, name: 'Hana', source_id: 'page' }) as TextMentionResponse

describe('mentions grouped by person (#103)', () => {
  it('groups by linked person with Unlinked last and never repeats a group', () => {
    const groups = groupMentionsByPerson([
      mention('1', null),
      mention('2', 'hana'),
      mention('3', 'tomas'),
      // A later batch can still bring an earlier person's mention.
      mention('4', 'hana'),
    ])
    expect(
      groups.map((group) => [group.key, group.records.map((item) => item.mention_id)]),
    ).toEqual([
      ['hana', ['2', '4']],
      ['tomas', ['3']],
      ['unlinked', ['1']],
    ])
  })

  it('pages the scope in person order and names each group', async () => {
    api.mentions.mockImplementation(({ query }) =>
      Promise.resolve({
        data: query.cursor
          ? { items: [mention('3', null)], cursor: null, total_count: 3 }
          : { items: [mention('1', 'hana'), mention('2', 'hana')], cursor: 'next', total_count: 3 },
      }),
    )
    api.entity.mockResolvedValue({ data: { entity_id: 'hana', name: 'Hana Sidebar' } })
    let model!: ReturnType<typeof useScanMentionsByPerson>
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(
      defineComponent({
        setup() {
          model = useScanMentionsByPerson({ 'filter.page_source_id': ['page'] })
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    await flushPromises()
    expect(api.mentions.mock.calls[0]![0].query).toMatchObject({
      'filter.page_source_id': ['page'],
      sort: 'person',
      sort_direction: 'asc',
    })
    expect(model.groups.value.map((group) => model.personName(group.personId))).toEqual([
      'Hana Sidebar',
    ])
    await model.loadMore()
    await flushPromises()
    expect(model.groups.value.map((group) => model.personName(group.personId))).toEqual([
      'Hana Sidebar',
      'Unlinked',
    ])
    expect(model.hasNextPage.value).toBe(false)
    wrapper.unmount()
    client.clear()
  })

  it('restores the person view from the URL', () => {
    expect(readSidebarState({ mention_view: 'person' }).mentionView).toBe('person')
    expect(sidebarQuery({ mentionView: 'person' })).toEqual({ mention_view: 'person' })
  })
})
