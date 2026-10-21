import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { usePatchEntityMutation } from '@/query/entities'
import { useReviewFacesMutation } from '@/query/faces'
import PersonPortrait from '@/components/custom/PersonPortrait.vue'
import { queryKeys } from '@/query/keys'

const mocks = vi.hoisted(() => ({ crop: vi.fn(), patchEntity: vi.fn(), patchFaces: vi.fn() }))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  getFaceAlignedCropRouteApiV1FacesDetectionIdAlignedCropGet: mocks.crop,
  patchEntityRouteApiV1EntitiesEntityIdPatch: mocks.patchEntity,
  patchFaceBatchRouteApiV1FacesBatchPatch: mocks.patchFaces,
}))

beforeEach(() => {
  mocks.crop.mockReset()
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:portrait'), revokeObjectURL: vi.fn() })
})
afterEach(() => vi.unstubAllGlobals())

function mountPortrait(faceId?: string) {
  const queryClient = new QueryClient()
  return {
    queryClient,
    wrapper: mount(PersonPortrait, {
      props: { name: 'Ada Novak', faceId },
      global: { plugins: [[VueQueryPlugin, { queryClient }]] },
    }),
  }
}

describe('canonical person media', () => {
  it('uses the saved face directly and drops stale media when the selection disappears', async () => {
    mocks.crop.mockResolvedValue({ data: new Blob(['portrait']) })
    const { wrapper, queryClient } = mountPortrait('saved-face-outside-evidence-page')
    await flushPromises()
    expect(mocks.crop).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { detection_id: 'saved-face-outside-evidence-page' },
        responseType: 'blob',
      }),
    )
    expect(
      queryClient.getQueryData(
        queryKeys.faceCrops.aligned('saved-face-outside-evidence-page', 256),
      ),
    ).toBeInstanceOf(Blob)
    expect(wrapper.findComponent({ name: 'AvatarImage' }).props('src')).toBe('blob:portrait')
    await wrapper.setProps({ faceId: null })
    expect(wrapper.text()).toContain('AN')
    expect(wrapper.findComponent({ name: 'AvatarImage' }).props('src')).toBe('')
    wrapper.unmount()
    queryClient.clear()
  })

  it('keeps initials for no-face and failed authenticated media responses', async () => {
    const { wrapper, queryClient } = mountPortrait()
    await flushPromises()
    expect(mocks.crop).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('AN')
    mocks.crop.mockRejectedValue(new Error('media unavailable'))
    await wrapper.setProps({ faceId: 'missing-media-face' })
    await flushPromises()
    expect(wrapper.text()).toContain('AN')
    expect(wrapper.find('[data-slot="avatar-image-skeleton"]').exists()).toBe(false)
    expect(mocks.crop).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    queryClient.clear()
  })

  it('keeps the loaded portrait visible during a background refetch', async () => {
    mocks.crop.mockResolvedValueOnce({ data: new Blob(['portrait']) })
    const { wrapper, queryClient } = mountPortrait('saved-face')
    await flushPromises()
    let finish!: (value: { data: Blob }) => void
    mocks.crop.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    const refresh = queryClient.invalidateQueries({ queryKey: queryKeys.faceCrops.all })
    await flushPromises()
    expect(wrapper.findComponent({ name: 'AvatarImage' }).props('loading')).toBe(false)
    expect(wrapper.findComponent({ name: 'AvatarImage' }).props('src')).toBe('blob:portrait')
    finish({ data: new Blob(['portrait']) })
    await refresh
    wrapper.unmount()
    queryClient.clear()
  })

  it('reuses crop bytes after portrait saves and face reviews', async () => {
    mocks.crop.mockResolvedValue({ data: new Blob(['portrait']) })
    mocks.patchEntity.mockResolvedValue({ data: { entity_id: 'ada', thumbnail_face_id: 'face' } })
    mocks.patchFaces.mockResolvedValue({ data: [{ detection_id: 'face' }] })
    const queryClient = new QueryClient()
    let patch!: ReturnType<typeof usePatchEntityMutation>
    let review!: ReturnType<typeof useReviewFacesMutation>
    const wrapper = mount(
      defineComponent({
        setup() {
          patch = usePatchEntityMutation()
          review = useReviewFacesMutation()
          return () => h(PersonPortrait, { name: 'Ada Novak', faceId: 'face' })
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
    )
    await flushPromises()
    await patch.mutateAsync({ entityId: 'ada', body: { thumbnail_face_id: 'face' } })
    await review.mutateAsync({ detectionIds: ['face'], action: 'verify' })
    await review.mutateAsync({ detectionIds: ['face'], action: 'unassign' })
    await flushPromises()
    expect(mocks.crop).toHaveBeenCalledTimes(1)
    expect(wrapper.findComponent({ name: 'AvatarImage' }).props('src')).toBe('blob:portrait')
    wrapper.unmount()
    queryClient.clear()
  })
})
