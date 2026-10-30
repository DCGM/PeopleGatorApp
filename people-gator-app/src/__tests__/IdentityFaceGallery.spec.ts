import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import IdentityFaceGallery from '@/components/custom/IdentityFaceGallery.vue'

const api = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  listFacesRouteApiV1FacesGet: api.list,
}))
const face = (id: string, entity = 'ada') => ({ detection_id: id, entity_id: entity })
const batch = (
  items: ReturnType<typeof face>[],
  cursor: string | null = null,
  total = items.length,
) => ({ data: { items, cursor, total_count: total } })
let wrapper: ReturnType<typeof mount>
let client: QueryClient
let visible: boolean
let frames: Map<number, FrameRequestCallback>
let frameId = 0
async function settle() {
  await flushPromises()
  const pending = [...frames.values()]
  frames.clear()
  for (const fn of pending) fn(0)
  await flushPromises()
}
async function showEnd() {
  visible = true
  window.dispatchEvent(new Event('scroll'))
  await settle()
}
function setup() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
  wrapper = mount(IdentityFaceGallery, {
    props: { personId: 'ada', name: 'Ada' },
    attachTo: document.body,
    global: {
      plugins: [[VueQueryPlugin, { queryClient: client }]],
      stubs: {
        IdentityReferenceFace: {
          props: ['faceId'],
          template: '<div role="listitem" :data-face-id="faceId" />',
        },
      },
    },
  })
}
beforeEach(() => {
  visible = false
  frames = new Map()
  api.list.mockReset()
  vi.stubGlobal('requestAnimationFrame', (fn: FrameRequestCallback) => {
    frames.set(++frameId, fn)
    return frameId
  })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id))
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement,
  ) {
    const top = this.hasAttribute('data-face-gallery-end') ? (visible ? 100 : 300) : 0
    return {
      top,
      bottom: top + 1,
      left: 0,
      right: 300,
      width: 300,
      height: 1,
      x: 0,
      y: top,
      toJSON() {},
    }
  })
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function (
    this: HTMLElement,
  ) {
    return this.getAttribute('data-slot') === 'scroll-area-viewport' ? 160 : 900
  })
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(1000)
})
afterEach(() => {
  wrapper?.unmount()
  client?.clear()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('identity face sentinel loading', () => {
  it('waits until the end is visible within the scroll area, deduplicates without a heading or counter', async () => {
    api.list
      .mockResolvedValueOnce(
        batch(
          Array.from({ length: 6 }, (_, i) => face(`a${i}`)),
          'next',
          7,
        ),
      )
      .mockResolvedValueOnce(batch([face('a5'), face('a6'), face('other', 'emil')], null, 7))
    setup()
    await settle()
    expect(api.list).toHaveBeenCalledTimes(1)
    expect(wrapper.find('h4').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('6 of 7')
    expect(wrapper.text()).not.toContain('Load more faces')
    await showEnd()
    expect(api.list.mock.calls[1]![0].query.cursor).toBe('next')
    expect(
      wrapper.findAll('[role="listitem"]').map((item) => item.attributes('data-face-id')),
    ).toEqual(['a0', 'a1', 'a2', 'a3', 'a4', 'a5', 'a6'])
    expect(wrapper.find('h4').exists()).toBe(false)
    await showEnd()
    expect(api.list).toHaveBeenCalledTimes(2)
  })

  it('fills spare space while the end remains visible and stops at the last cursor', async () => {
    api.list
      .mockResolvedValueOnce(batch([face('a')], 'second', 3))
      .mockResolvedValueOnce(batch([face('b')], 'third', 3))
      .mockResolvedValueOnce(batch([face('c')], null, 3))
    setup()
    await settle()
    await showEnd()
    await settle()
    await settle()
    expect(api.list.mock.calls.map(([arg]) => arg.query.cursor)).toEqual([null, 'second', 'third'])
    expect(wrapper.findAll('[role="listitem"]')).toHaveLength(3)
    expect(wrapper.find('h4').exists()).toBe(false)
    expect(wrapper.find('[data-face-gallery-end]').exists()).toBe(false)
  })

  it('does not overlap requests or keep observing after the gallery closes', async () => {
    let finish!: (value: ReturnType<typeof batch>) => void
    api.list.mockResolvedValueOnce(batch([face('a')], 'next', 2)).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    setup()
    await settle()
    await showEnd()
    expect(wrapper.text()).toContain('Loading more faces')
    await showEnd()
    await showEnd()
    expect(api.list).toHaveBeenCalledTimes(2)
    finish(batch([face('b')], null, 2))
    await settle()
    expect(wrapper.findAll('[role="listitem"]')).toHaveLength(2)
    wrapper.unmount()
    await showEnd()
    expect(api.list).toHaveBeenCalledTimes(2)
  })

  it('retains faces after a failed continuation, stops automatic retries and retries the same cursor explicitly', async () => {
    api.list
      .mockResolvedValueOnce(batch([face('a')], 'next', 2))
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(batch([face('b')], null, 2))
    setup()
    await settle()
    await showEnd()
    expect(wrapper.get('[role="alert"]').text()).toContain('Could not load more faces')
    expect(wrapper.findAll('[role="listitem"]')).toHaveLength(1)
    await showEnd()
    await settle()
    expect(api.list).toHaveBeenCalledTimes(2)
    await wrapper.get('[role="alert"] button').trigger('click')
    await settle()
    expect(api.list.mock.calls[2]![0].query.cursor).toBe('next')
    expect(wrapper.findAll('[role="listitem"]')).toHaveLength(2)
    expect(wrapper.find('h4').exists()).toBe(false)
  })
})
