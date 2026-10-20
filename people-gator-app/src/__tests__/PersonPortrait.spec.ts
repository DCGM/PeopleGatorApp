import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PersonPortrait from '@/components/custom/PersonPortrait.vue'
import { queryKeys } from '@/query/keys'

const mocks = vi.hoisted(() => ({ crop: vi.fn() }))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  getFaceAlignedCropRouteApiV1FacesDetectionIdAlignedCropGet: mocks.crop,
}))

beforeEach(() => {
  mocks.crop.mockReset()
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:portrait'), revokeObjectURL: vi.fn() })
})
afterEach(() => vi.unstubAllGlobals())

function mountPortrait(faceId?: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
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
        queryKeys.faces.alignedCrop('saved-face-outside-evidence-page', 256),
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
    wrapper.unmount()
    queryClient.clear()
  })
})
