import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  faces: vi.fn(),
  crop: vi.fn(),
  thumbnail: 'canonical-face' as string | null,
}))
vi.mock('@/query/faces', async () => {
  const { ref } = await import('vue')
  return {
    fetchFaces: mocks.faces,
    fetchFaceAlignedCrop: mocks.crop,
    useAssignFacesMutation: () => ({ status: ref('idle'), error: ref(null), mutate: vi.fn() }),
  }
})
vi.mock('@/query/entities', async () => {
  const { ref } = await import('vue')
  return {
    fetchEntity: vi.fn(),
    useMergeEntitiesMutation: () => ({ status: ref('idle'), error: ref(null), mutate: vi.fn() }),
  }
})
vi.mock('@/query/search', async () => {
  const { ref } = await import('vue')
  const query = (items: unknown[]) => ({
    data: ref({ pages: [{ items }] }),
    error: ref(null),
    isPending: ref(false),
    isFetching: ref(false),
  })
  return {
    useFaceSearchQuery: () => query([]),
    useEntitySearchQuery: () =>
      query([
        {
          entity_id: 'candidate',
          entity_type: 'person',
          name: 'Ada',
          thumbnail_face_id: mocks.thumbnail,
          matched_detection_ids: ['different-match'],
          face_score: 0.9,
        },
      ]),
  }
})
import { usePersonDiscovery } from '@/viewmodels/person-discovery'

async function discover() {
  let result!: ReturnType<typeof usePersonDiscovery>
  const queryClient = new QueryClient()
  const wrapper = mount(
    defineComponent({
      setup() {
        result = usePersonDiscovery('current-person', null, 'Ada', true)
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  )
  await flushPromises()
  const candidate = result.similarPeople.value[0]
  wrapper.unmount()
  queryClient.clear()
  return candidate
}

describe('discovery canonical portraits', () => {
  it('shows the matched face when the store persists no portrait', async () => {
    mocks.thumbnail = null
    expect(await discover()).toMatchObject({ thumbnailFaceId: 'different-match' })
    mocks.thumbnail = 'canonical-face'
  })

  it('uses metadata even when a different evidence face matched and needs no per-person face listing', async () => {
    let result!: ReturnType<typeof usePersonDiscovery>
    const queryClient = new QueryClient()
    const wrapper = mount(
      defineComponent({
        setup() {
          result = usePersonDiscovery('current-person', null, 'Ada', true)
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
    )
    await flushPromises()
    expect(result.similarPeople.value[0]).toMatchObject({
      thumbnailFaceId: 'canonical-face',
      matchedFaceIds: ['different-match'],
    })
    expect(mocks.faces).not.toHaveBeenCalled()
    wrapper.unmount()
    queryClient.clear()
  })
})
