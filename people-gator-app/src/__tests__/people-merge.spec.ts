import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, ref } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { beforeEach, expect, it, vi } from 'vitest'
import { AxiosError } from 'axios'
import { usePeopleMerge } from '@/viewmodels/people-merge'
import { queryKeys } from '@/query/keys'

const api = vi.hoisted(() => ({ single: vi.fn(), batch: vi.fn(), get: vi.fn(), allowed: true }))
vi.mock('@/client', () => ({
  mergeEntityRouteApiV1EntitiesTargetEntityIdMergePost: api.single,
  mergeEntityBatchRouteApiV1EntitiesTargetEntityIdMergeBatchPost: api.batch,
  getEntityRouteApiV1EntitiesEntityIdGet: api.get,
}))
vi.mock('@/composables/can-annotate', () => ({ useHasScope: () => permission }))
const permission = ref(true)
const people = ref([
  { id: 'a', name: 'Ada' },
  { id: 'b', name: 'Bea' },
  { id: 'c', name: 'Cia' },
])
const scope = ref('query-one')
const loading = ref(false)
let state: ReturnType<typeof usePeopleMerge>
let client: QueryClient
function setup() {
  client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  const wrapper = mount(
    defineComponent({
      setup() {
        state = usePeopleMerge(people, scope, loading)
        return () => null
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
  )
  return wrapper
}
const click = (id: string, shiftKey = false) => state.toggle(id, { shiftKey })
beforeEach(() => {
  vi.clearAllMocks()
  permission.value = true
  people.value = [
    { id: 'a', name: 'Ada' },
    { id: 'b', name: 'Bea' },
    { id: 'c', name: 'Cia' },
  ]
  scope.value = 'query-one'
  loading.value = false
  for (const fn of [api.single, api.batch])
    fn.mockImplementation(async ({ path }) => ({
      data: {
        target_entity_id: path.target_entity_id,
        merged_entity: { entity_id: path.target_entity_id, name: 'Merged' },
      },
    }))
})
it('retains insertion order across reorder and appends backward Shift ranges in display order', async () => {
  const wrapper = setup()
  click('c')
  click('a', true)
  expect([...state.selectedIds.value]).toEqual(['c', 'a', 'b'])
  people.value = [...people.value].reverse()
  await flushPromises()
  expect(state.selected.value.map((p) => p.id)).toEqual(['c', 'a', 'b'])
  click('a')
  click('a')
  expect(state.selected.value.map((p) => p.id)).toEqual(['c', 'b', 'a'])
  state.clear()
  click('b', true)
  expect([...state.selectedIds.value]).toEqual(['b'])
  wrapper.unmount()
})
it.each(['first', 'last'] as const)(
  'submits immediately to the %s target, clears selection and refreshes shared caches',
  async (which) => {
    const wrapper = setup()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    client.setQueryData(queryKeys.entities.detail('a'), { entity_id: 'a' })
    click('a')
    click('b')
    click('c')
    await state.merge(which)
    const target = which === 'first' ? 'a' : 'c'
    expect(api.batch).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({
        path: { target_entity_id: target },
        body: { source_entity_ids: which === 'first' ? ['b', 'c'] : ['a', 'b'] },
      }),
    )
    expect(api.single).not.toHaveBeenCalled()
    expect(state.selectedIds.value.size).toBe(0)
    expect(state.message.value).toBe('People merged.')
    expect(client.getQueryData(queryKeys.entities.detail(target))).toMatchObject({ name: 'Merged' })
    for (const key of [
      queryKeys.entities.all,
      queryKeys.faces.all,
      queryKeys.textMentions.all,
      queryKeys.search.all,
    ])
      expect(invalidate).toHaveBeenCalledWith({ queryKey: key })
    wrapper.unmount()
  },
)
it('uses one single merge for two people and freezes the request against repeated submit and selection changes', async () => {
  let finish!: (value: unknown) => void
  api.single.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      }),
  )
  const wrapper = setup()
  click('b')
  click('a')
  const request = state.merge('last')
  await flushPromises()
  click('c')
  state.clear()
  await state.merge('first')
  expect([...state.selectedIds.value]).toEqual(['b', 'a'])
  expect(api.single).toHaveBeenCalledExactlyOnceWith(
    expect.objectContaining({
      path: { target_entity_id: 'a' },
      body: { source_entity_id: 'b' },
    }),
  )
  finish({ data: { target_entity_id: 'a', merged_entity: { entity_id: 'a' } } })
  await request
  expect(state.busy.value).toBe(false)
  wrapper.unmount()
})
it('does not select unloaded people or merge without permission/two people', async () => {
  const wrapper = setup()
  click('missing')
  click('a')
  await state.merge('first')
  expect(api.single).not.toHaveBeenCalled()
  permission.value = false
  click('b')
  await state.merge('last')
  expect(api.single).not.toHaveBeenCalled()
  wrapper.unmount()
})
it('keeps selection on append, prunes unavailable results, and clears on query/filter changes', async () => {
  const wrapper = setup()
  click('a')
  click('b')
  people.value.push({ id: 'd', name: 'Dee' })
  await flushPromises()
  expect([...state.selectedIds.value]).toEqual(['a', 'b'])
  people.value = people.value.filter((p) => p.id !== 'a')
  await flushPromises()
  expect([...state.selectedIds.value]).toEqual(['b'])
  scope.value = 'another-filter'
  expect(state.selectedIds.value.size).toBe(0)
  loading.value = true
  click('c')
  expect(state.selectedIds.value.size).toBe(0)
  wrapper.unmount()
})
it.each([403, 409, 422, undefined])(
  'preserves selection on failure (%s) and permits recovery',
  async (status) => {
    const wrapper = setup()
    const error = new AxiosError('failed')
    if (status) error.response = { status } as never
    api.single.mockRejectedValueOnce(error)
    click('a')
    click('b')
    await state.merge('first')
    expect(state.selected.value.map((p) => p.id)).toEqual(['a', 'b'])
    expect(state.message.value).not.toBe('People merged.')
    expect(state.busy.value).toBe(false)
    await state.merge('last')
    expect(state.message.value).toBe('People merged.')
    wrapper.unmount()
  },
)
it('reconciles only confirmed missing records after a stale merge fails', async () => {
  const wrapper = setup()
  const missing = new AxiosError('missing')
  missing.response = { status: 404 } as never
  api.batch.mockRejectedValueOnce(missing)
  api.get.mockImplementation(({ path }) =>
    path.entity_id === 'b' ? Promise.reject(missing) : Promise.resolve({ data: {} }),
  )
  click('a')
  click('b')
  click('c')
  await state.merge('last')
  expect(state.selected.value.map((p) => p.id)).toEqual(['a', 'c'])
  expect(state.message.value).toContain('unavailable')
  wrapper.unmount()
})

it.each([
  { targetEntityId: 'a', sourceEntityIds: [] },
  { targetEntityId: 'a', sourceEntityIds: ['b', 'b'] },
  { targetEntityId: 'a', sourceEntityIds: ['a'] },
  { targetEntityId: '', sourceEntityIds: ['b'] },
])('rejects invalid merge payloads before an API request: %j', async (payload) => {
  const { useMergeEntitiesMutation } = await import('@/query/entities')
  let mutation!: ReturnType<typeof useMergeEntitiesMutation>
  const wrapper = mount(
    defineComponent({
      setup() {
        mutation = useMergeEntitiesMutation()
        return () => null
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] } },
  )
  await expect(mutation.mutateAsync(payload)).rejects.toThrow('Select distinct people')
  expect(api.single).not.toHaveBeenCalled()
  expect(api.batch).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('clears selection after a query change during a failed pending request', async () => {
  let fail!: (error: unknown) => void
  api.single.mockImplementation(
    () =>
      new Promise((_resolve, reject) => {
        fail = reject
      }),
  )
  const wrapper = setup()
  click('a')
  click('b')
  const pending = state.merge('first')
  await flushPromises()
  scope.value = 'different-query'
  fail(new AxiosError('network'))
  await pending
  expect(state.selectedIds.value.size).toBe(0)
  expect(state.message.value).toBe('')
  wrapper.unmount()
})

it('makes card selection additive, keeps existing selection order and toggles only via controls', async () => {
  const wrapper = setup()
  click('c')
  state.add('a', { shiftKey: false })
  state.add('c', { shiftKey: false })
  expect([...state.selectedIds.value]).toEqual(['c', 'a'])
  // Clicking an already-selected card must not replace the range anchor (Ada).
  state.add('c', { shiftKey: true })
  expect([...state.selectedIds.value]).toEqual(['c', 'a', 'b'])
  click('a')
  expect([...state.selectedIds.value]).toEqual(['c', 'b'])
  click('a')
  expect([...state.selectedIds.value]).toEqual(['c', 'b', 'a'])
  wrapper.unmount()
})

it('blocks additive card selection during pending merge and loading', async () => {
  const wrapper = setup()
  loading.value = true
  state.add('a', { shiftKey: false })
  expect(state.selectedIds.value.size).toBe(0)
  loading.value = false
  click('a')
  click('b')
  let finish!: (value: unknown) => void
  api.single.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      }),
  )
  const pending = state.merge('first')
  await flushPromises()
  state.add('c', { shiftKey: false })
  expect([...state.selectedIds.value]).toEqual(['a', 'b'])
  finish({ data: { target_entity_id: 'a', merged_entity: { entity_id: 'a' } } })
  await pending
  wrapper.unmount()
})
