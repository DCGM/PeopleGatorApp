import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// People screens use the typed person API (#123); generic entity endpoints carry
// no names, life dates or their filters and sorts.
const api = vi.hoisted(() => ({
  listPeople: vi.fn(),
  searchPeople: vi.fn(),
  getPerson: vi.fn(),
  patchPerson: vi.fn(),
  listEntities: vi.fn(),
  searchEntities: vi.fn(),
  getEntity: vi.fn(),
  patchEntity: vi.fn(),
}))
vi.mock('@/client', () => ({
  listPeopleRouteApiV1PeopleGet: api.listPeople,
  searchPeopleGetApiV1SearchPeopleGet: api.searchPeople,
  getPersonRouteApiV1PeopleEntityIdGet: api.getPerson,
  patchPersonRouteApiV1PeopleEntityIdPatch: api.patchPerson,
  listEntitiesRouteApiV1EntitiesGet: api.listEntities,
  searchEntitiesGetApiV1SearchEntitiesGet: api.searchEntities,
  getEntityRouteApiV1EntitiesEntityIdGet: api.getEntity,
  patchEntityRouteApiV1EntitiesEntityIdPatch: api.patchEntity,
}))
import { usePeopleSearch } from '@/viewmodels/people-search'
import { usePatchPersonMutation, usePersonQuery } from '@/query/people'

const person = {
  entity_id: 'p1',
  entity_type: 'person',
  name: 'Karel Vrba',
  user_id: 'u1',
  birth_date: '1890-03-14',
  death_date: '1962-11-02',
}
const page = { items: [person], limit: 12, total_count: 1, cursor: null }

function run<T>(setup: () => T) {
  let result!: T
  const wrapper = mount(
    defineComponent({
      setup() {
        result = setup()
        return () => h('div')
      },
    }),
    {
      global: {
        plugins: [
          [
            VueQueryPlugin,
            { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
          ],
        ],
      },
    },
  )
  return { result, wrapper }
}

describe('typed person API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.listPeople.mockResolvedValue({ data: page })
    api.searchPeople.mockResolvedValue({ data: page })
    api.getPerson.mockResolvedValue({ data: person })
    api.patchPerson.mockResolvedValue({ data: { ...person, surname: 'Vrba' } })
  })

  it('browses and searches people with life-date ranges and person sorts', async () => {
    const term = ref('')
    const { result, wrapper } = run(() =>
      usePeopleSearch(
        term,
        'all',
        12,
        { 'filter.birth_date_from': '1870-01-01', 'filter.death_date_to': '1949-12-31' },
        true,
        { field: 'surname', direction: 'asc' },
      ),
    )
    await flushPromises()
    expect(api.listPeople.mock.lastCall?.[0].query).toMatchObject({
      'filter.birth_date_from': '1870-01-01',
      'filter.death_date_to': '1949-12-31',
      sort: 'surname',
    })
    expect(api.listPeople.mock.lastCall?.[0].query).not.toHaveProperty('filter.entity_type')
    expect(result.people.value[0]).toMatchObject({ name: 'Karel Vrba', lifeSpan: '1890–1962' })

    term.value = 'Karel'
    await flushPromises()
    expect(api.searchPeople.mock.lastCall?.[0].query).toMatchObject({
      'query.text': ['Karel'],
      'filter.birth_date_from': '1870-01-01',
      sort: 'surname',
    })
    expect(api.listEntities).not.toHaveBeenCalled()
    expect(api.searchEntities).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('reads and patches a person through /people', async () => {
    const { result, wrapper } = run(() => ({
      person: usePersonQuery('p1'),
      patch: usePatchPersonMutation(),
    }))
    await flushPromises()
    expect(api.getPerson).toHaveBeenCalledWith(
      expect.objectContaining({ path: { entity_id: 'p1' } }),
    )
    expect(result.person.data.value?.birth_date).toBe('1890-03-14')
    await result.patch.mutateAsync({ entityId: 'p1', body: { surname: 'Vrba', death_date: null } })
    expect(api.patchPerson).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { entity_id: 'p1' },
        body: { surname: 'Vrba', death_date: null },
      }),
    )
    expect(api.getEntity).not.toHaveBeenCalled()
    expect(api.patchEntity).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
