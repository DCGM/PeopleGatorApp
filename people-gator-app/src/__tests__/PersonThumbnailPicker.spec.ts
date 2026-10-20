import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, DOMWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PersonThumbnailPicker from '@/components/custom/PersonThumbnailPicker.vue'
import { queryKeys } from '@/query/keys'

const mocks = vi.hoisted(() => ({ list: vi.fn(), patch: vi.fn() }))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  listFacesRouteApiV1FacesGet: mocks.list,
  patchEntityRouteApiV1EntitiesEntityIdPatch: mocks.patch,
}))

beforeEach(() => {
  mocks.list.mockReset().mockResolvedValue({
    data: { items: [{ detection_id: 'other-face' }], limit: 24, cursor: null },
  })
  mocks.patch.mockReset()
})

async function openPicker() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
  const wrapper = mount(PersonThumbnailPicker, {
    attachTo: document.body,
    props: { personId: 'ada', name: 'Ada Novak', selectedFaceId: 'saved-face', mode: 'manual' },
    global: { plugins: [[VueQueryPlugin, { queryClient }]], stubs: { PersonPortrait: true } },
  })
  await wrapper.get('button').trigger('click')
  await flushPromises()
  await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
  return { wrapper, content: new DOMWrapper(document.body), queryClient, invalidate }
}

describe('portrait selection', () => {
  it('lists all linked faces without evidence filters, saves and refreshes identity caches', async () => {
    mocks.patch.mockResolvedValue({
      data: { entity_id: 'ada', thumbnail_face_id: 'other-face', thumbnail_mode: 'manual' },
    })
    const { wrapper, content, queryClient, invalidate } = await openPicker()
    expect(mocks.list.mock.lastCall?.[0].query).toMatchObject({
      'filter.entity_id': ['ada'],
      limit: 24,
    })
    expect(mocks.list.mock.lastCall?.[0].query).not.toHaveProperty('filter.entity_link_state')
    await content.get('[aria-label="Use linked face 1 as portrait"]').trigger('click')
    await flushPromises()
    expect(mocks.patch.mock.lastCall?.[0]).toMatchObject({
      path: { entity_id: 'ada' },
      body: { thumbnail_face_id: 'other-face' },
    })
    expect(queryClient.getQueryData(queryKeys.entities.detail('ada'))).toMatchObject({
      thumbnail_face_id: 'other-face',
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.entities.lists() })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.search.all })
    expect(content.find('[role="dialog"]').exists()).toBe(false)
    wrapper.unmount()
    queryClient.clear()
  })

  it('resets using explicit null and keeps failures recoverable without changing saved props', async () => {
    mocks.patch.mockRejectedValueOnce(new Error('save failed')).mockResolvedValueOnce({
      data: {
        entity_id: 'ada',
        thumbnail_face_id: 'automatic-face',
        thumbnail_mode: 'automatic',
      },
    })
    const { wrapper, content, queryClient } = await openPicker()
    const reset = () =>
      content.findAll('button').find((button) => button.text() === 'Use automatic')!
    await reset().trigger('click')
    await flushPromises()
    expect(mocks.patch.mock.lastCall?.[0].body).toEqual({ thumbnail_face_id: null })
    expect(content.get('[role="alert"]').text()).toContain('Save not confirmed')
    expect(wrapper.props('selectedFaceId')).toBe('saved-face')
    expect(queryClient.getQueryData(queryKeys.entities.detail('ada'))).toBeUndefined()
    await reset().trigger('click')
    await flushPromises()
    expect(queryClient.getQueryData(queryKeys.entities.detail('ada'))).toMatchObject({
      thumbnail_mode: 'automatic',
    })
    wrapper.unmount()
    queryClient.clear()
  })

  it('loads later choices through cursor pagination', async () => {
    mocks.list
      .mockResolvedValueOnce({
        data: { items: [{ detection_id: 'first' }], limit: 24, cursor: 'next' },
      })
      .mockResolvedValueOnce({
        data: { items: [{ detection_id: 'later' }], limit: 24, cursor: null },
      })
    const { wrapper, content, queryClient } = await openPicker()
    await content
      .findAll('button')
      .find((button) => button.text() === 'Load more faces')!
      .trigger('click')
    await flushPromises()
    expect(mocks.list.mock.lastCall?.[0].query.cursor).toBe('next')
    expect(content.findAll('[aria-label^="Use linked face"]')).toHaveLength(2)
    wrapper.unmount()
    queryClient.clear()
  })
})
