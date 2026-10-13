import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ApiKeyResponse, EntityResponse, UserFilterOption } from '@/client'

type Lookup<T> = (options: {
  query: { q: string }
}) => Promise<{ data: { items: T[]; cursor: null } }>
const mocks = vi.hoisted(() => ({
  entity: vi.fn<() => Promise<{ data: EntityResponse }>>(),
  patch: vi.fn<() => Promise<{ data: EntityResponse }>>(),
  users: vi.fn<Lookup<UserFilterOption>>(),
  keys: vi.fn<Lookup<ApiKeyResponse>>(),
}))
vi.mock('@/client', () => ({
  getEntityRouteApiV1EntitiesEntityIdGet: mocks.entity,
  patchEntityRouteApiV1EntitiesEntityIdPatch: mocks.patch,
  listUserFilterOptionsRouteApiV1UserFilterOptionsGet: mocks.users,
  listApiKeysRouteApiV1ApiKeysGet: mocks.keys,
}))
vi.mock('@/query/faces', () => ({
  useFaceListQuery: () => ({ data: ref(undefined), isPending: ref(false) }),
}))
vi.mock('@/query/text-mentions', () => ({
  useTextMentionListQuery: () => ({ data: ref(undefined), isPending: ref(false) }),
}))

import PersonProcessingDetails from '@/components/custom/PersonProcessingDetails.vue'
import { usePersonDetail } from '@/viewmodels/person-detail'

const historical: EntityResponse = {
  entity_id: 'person-ada',
  entity_type: 'person',
  name: 'Ada Lovelace',
  user_id: 'original-owner',
}
const processed: EntityResponse = {
  ...historical,
  last_touched_at: '2026-10-13T12:34:56Z',
  last_touched_by_user_id: 'pipeline-user',
  last_touched_by_api_key_id: 'pipeline-key',
}

function harness() {
  const personId = ref(historical.entity_id)
  let result!: ReturnType<typeof usePersonDetail>
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(
    defineComponent({
      setup() {
        result = usePersonDetail(personId)
        return () =>
          result.entity.value
            ? h(PersonProcessingDetails, {
                processing: result.processing.value,
                refreshing: result.processingRefreshing.value,
                onRefresh: result.refreshProcessing,
              })
            : null
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  )
  return {
    personId,
    wrapper,
    get result() {
      return result
    },
    cleanup() {
      wrapper.unmount()
      queryClient.clear()
    },
  }
}

describe('person processing information', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.entity.mockResolvedValue({ data: historical })
    mocks.users.mockImplementation(({ query }) =>
      Promise.resolve({
        data: {
          items: [
            {
              user_id: query.q,
              display_name: query.q === 'pipeline-user' ? 'Pipeline account' : 'Annotator',
            },
          ],
          cursor: null,
        },
      }),
    )
    mocks.keys.mockResolvedValue({
      data: {
        items: [
          {
            api_key_id: 'pipeline-key',
            user_id: 'pipeline-user',
            display_name: 'Archive importer',
            identifier: 'archive-ingest',
          },
        ],
        cursor: null,
      },
    })
  })

  it('keeps historical processing unknown without substituting the record owner', async () => {
    const app = harness()
    await flushPromises()
    expect(app.wrapper.text()).toContain('No processing recorded')
    expect(app.wrapper.find('time').exists()).toBe(false)
    expect(mocks.users).not.toHaveBeenCalled()
    expect(mocks.keys).not.toHaveBeenCalled()
    app.cleanup()
  })

  it('shows the last actor and refreshes attribution after a profile edit', async () => {
    mocks.entity.mockResolvedValue({ data: processed })
    const app = harness()
    await flushPromises()
    expect(app.wrapper.get('time').attributes('datetime')).toBe(processed.last_touched_at)
    expect(app.wrapper.text()).toContain('Pipeline account')
    expect(app.wrapper.text()).toContain('Archive importer (archive-ingest)')
    expect(mocks.users.mock.lastCall?.[0].query.q).toBe('pipeline-user')
    expect(mocks.keys.mock.lastCall?.[0].query.q).toBe('pipeline-key')
    mocks.patch.mockResolvedValue({
      data: {
        ...processed,
        name: 'Ada',
        last_touched_at: '2026-10-13T12:35:01Z',
        last_touched_by_user_id: 'annotator-user',
        last_touched_by_api_key_id: null,
      },
    })
    app.result.updateProfile({ name: 'Ada', shortDescription: '', article: '', aliases: [] })
    await flushPromises()
    expect(app.wrapper.get('time').attributes('datetime')).toBe('2026-10-13T12:35:01Z')
    expect(app.wrapper.text()).toContain('Annotator')
    expect(app.wrapper.text()).toContain('No API key')
    expect(app.wrapper.text()).not.toContain('Archive importer')
    app.cleanup()
  })

  it('refreshes pipeline updates and falls back to IDs if actor lookups fail', async () => {
    const app = harness()
    await flushPromises()
    mocks.entity.mockResolvedValue({ data: processed })
    mocks.users.mockRejectedValue(new Error('unavailable'))
    mocks.keys.mockRejectedValue(new Error('unavailable'))
    await app.wrapper.get('button[aria-label="Refresh processing information"]').trigger('click')
    await flushPromises()
    expect(mocks.entity).toHaveBeenCalledTimes(2)
    expect(app.wrapper.text()).toContain('pipeline-user')
    expect(app.wrapper.text()).toContain('pipeline-key')
    expect(app.wrapper.get('time').attributes('datetime')).toBe(processed.last_touched_at)
    // Navigating to a historical record must discard the previous attribution.
    mocks.entity.mockResolvedValue({ data: { ...historical, entity_id: 'historical-person' } })
    app.personId.value = 'historical-person'
    await flushPromises()
    expect(app.wrapper.text()).toContain('No processing recorded')
    expect(app.wrapper.text()).not.toContain('pipeline-user')
    app.cleanup()
  })
})
