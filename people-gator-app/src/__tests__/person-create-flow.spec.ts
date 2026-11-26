import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// #176: faces and mentions create people in place through the typed person API.
const api = vi.hoisted(() => ({
  putPerson: vi.fn(),
  createEntity: vi.fn(),
  patchMentions: vi.fn(),
  deleteMentions: vi.fn(),
  createMention: vi.fn(),
}))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  putPersonRouteApiV1PeopleEntityIdPut: api.putPerson,
  createEntityRouteApiV1EntitiesPost: api.createEntity,
  patchTextMentionBatchRouteApiV1TextMentionsBatchPatch: api.patchMentions,
  deleteTextMentionBatchRouteApiV1TextMentionsBatchDelete: api.deleteMentions,
  createTextMentionRouteApiV1TextMentionsPost: api.createMention,
}))
import { usePersonCreateFlow } from '@/viewmodels/person-create-flow'
import {
  assignTextMentions,
  useCreateTextMentionMutation,
  useDeleteTextMentionsMutation,
} from '@/query/text-mentions'

function run<T>(setup: () => T) {
  let result!: T
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  mount(
    defineComponent({
      setup() {
        result = setup()
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
  )
  return { result, client }
}

const person = (entity_id: string) => ({
  data: { entity_id, entity_type: 'person', name: 'Jan Bulk', user_id: 'u1' },
})

beforeEach(() => vi.clearAllMocks())

describe('in-place person creation (#176)', () => {
  it('PUTs a client UUID, then links; a retry after a failed link reuses it', async () => {
    const ids = ['first-uuid', 'second-uuid']
    const { result: flow, client } = run(() => usePersonCreateFlow(() => ids.shift()!))
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    api.putPerson.mockImplementation(({ path }) => Promise.resolve(person(path.entity_id)))
    const link = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue([])

    await expect(flow.createAndLink({ name: 'Jan Bulk' }, link)).rejects.toThrow('offline')
    expect(flow.pending.value).toBe(false)
    const created = await flow.createAndLink(
      { name: 'Jan Bulk', shortDescription: 'Parish clerk' },
      link,
    )

    expect(created.entity_id).toBe('first-uuid')
    expect(api.putPerson.mock.calls.map(([options]) => options)).toEqual([
      {
        path: { entity_id: 'first-uuid' },
        body: { entity_type: 'person', name: 'Jan Bulk', short_description: null },
        throwOnError: true,
      },
      {
        path: { entity_id: 'first-uuid' },
        body: { entity_type: 'person', name: 'Jan Bulk', short_description: 'Parish clerk' },
        throwOnError: true,
      },
    ])
    expect(link.mock.calls).toEqual([['first-uuid'], ['first-uuid']])
    // The generic entity route is no longer used.
    expect(api.createEntity).not.toHaveBeenCalled()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['search'] })

    // After success, the next person gets a new UUID.
    await flow.createAndLink({ name: 'Eva' }, link)
    expect(api.putPerson.mock.lastCall![0].path.entity_id).toBe('second-uuid')
  })

  it('forgets the pending UUID when cancelled', async () => {
    const ids = ['a', 'b']
    const { result: flow } = run(() => usePersonCreateFlow(() => ids.shift()!))
    api.putPerson.mockRejectedValueOnce(new Error('down'))
    await expect(flow.createAndLink({ name: 'Jan' }, vi.fn())).rejects.toThrow('down')
    flow.cancel()
    api.putPerson.mockImplementation(({ path }) => Promise.resolve(person(path.entity_id)))
    await flow.createAndLink({ name: 'Jan' }, vi.fn())
    expect(api.putPerson.mock.lastCall![0].path.entity_id).toBe('b')
  })
})

describe('mention mutations (#176)', () => {
  it('links, unlinks and deletes in batches and creates unlinked mentions', async () => {
    api.patchMentions.mockImplementation(({ body }) =>
      Promise.resolve({ data: body.map((item: { mention_id: string }) => item) }),
    )
    const ids = Array.from({ length: 51 }, (_value, index) => `m${index}`)
    await assignTextMentions(ids, 'jan')
    expect(api.patchMentions).toHaveBeenCalledTimes(2)
    expect(api.patchMentions.mock.calls[0]![0].body[0]).toEqual({
      mention_id: 'm0',
      entity_id: 'jan',
      entity_link_state: 'manual',
    })
    expect(api.patchMentions.mock.calls[1]![0].body).toHaveLength(1)
    await assignTextMentions(['m0'], null)
    expect(api.patchMentions.mock.lastCall![0].body).toEqual([
      { mention_id: 'm0', entity_id: null, entity_link_state: null },
    ])
    api.patchMentions.mockResolvedValueOnce({ data: [null] })
    await expect(assignTextMentions(['gone'], 'jan')).rejects.toThrow('Mention unavailable')

    const { result } = run(() => ({
      remove: useDeleteTextMentionsMutation(),
      create: useCreateTextMentionMutation(),
    }))
    api.deleteMentions.mockResolvedValue({ data: 2 })
    expect(await result.remove.mutateAsync(['m1', 'm2', 'm1'])).toBe(2)
    expect(api.deleteMentions).toHaveBeenCalledWith({ body: ['m1', 'm2'], throwOnError: true })

    api.createMention.mockResolvedValue({ data: { mention_id: 'new' } })
    await result.create.mutateAsync({ name: 'Marta', context: 'Marta wrote.', source_id: 's' })
    // An unlinked mention is sent without a link state, which needs an entity.
    expect(api.createMention.mock.lastCall![0].body).toEqual({
      name: 'Marta',
      context: 'Marta wrote.',
      source_id: 's',
    })
    await result.create.mutateAsync({ name: 'Jan', source_id: 's', entity_id: 'jan' })
    expect(api.createMention.mock.lastCall![0].body.entity_link_state).toBe('manual')
    await flushPromises()
  })
})
