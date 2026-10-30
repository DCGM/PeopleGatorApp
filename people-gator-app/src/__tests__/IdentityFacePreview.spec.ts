import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import IdentityFacePreview from '@/components/custom/IdentityFacePreview.vue'
import SimilarPersonItem from '@/components/custom/SimilarPersonItem.vue'
import { queryKeys } from '@/query/keys'

const mocks = vi.hoisted(() => ({ list: vi.fn(), crop: vi.fn() }))
vi.mock('@/client', async (original) => ({
  ...(await original<typeof import('@/client')>()),
  listFacesRouteApiV1FacesGet: mocks.list,
  getFaceAlignedCropRouteApiV1FacesDetectionIdAlignedCropGet: mocks.crop,
}))
const face = (id: string, entity = 'ada') => ({ detection_id: id, entity_id: entity })
const batch = (
  items: ReturnType<typeof face>[],
  cursor: string | null = null,
  total = items.length,
) => ({ data: { items, cursor, total_count: total } })
let mounted: ReturnType<typeof mount>
let client: QueryClient
function setup() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
  mounted = mount(IdentityFacePreview, {
    props: { personId: 'ada', name: 'Ada Novak' },
    attachTo: document.body,
    global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
  })
  return mounted
}
async function dismiss() {
  document
    .querySelector('[role="dialog"]')!
    .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await flushPromises()
}
async function click(label: string) {
  const button = [...document.querySelectorAll('button')].find(
    (b) => b.textContent?.trim() === label || b.getAttribute('aria-label') === label,
  )!
  expect(button, label).toBeTruthy()
  button.click()
  await flushPromises()
}
beforeEach(() => {
  mocks.list.mockReset().mockResolvedValue(batch([]))
  mocks.crop.mockReset().mockResolvedValue({ data: new Blob(['face']) })
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
  vi.stubGlobal('URL', { createObjectURL: () => 'blob:face', revokeObjectURL: vi.fn() })
})
afterEach(() => {
  mounted?.unmount()
  client?.clear()
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

describe('in-place identity faces', () => {
  it('keeps candidate preview, profile navigation and assignment independent of reference browsing', async () => {
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    mounted = mount(SimilarPersonItem, {
      props: {
        person: {
          id: 'ada',
          name: 'Ada Novak',
          score: 1,
          nerMentions: 0,
          detections: 1,
          source: 'page',
        },
      },
      attachTo: document.body,
      global: {
        plugins: [[VueQueryPlugin, { queryClient: client }]],
        stubs: { RouterLink: RouterLinkStub, PersonPortrait: true },
      },
    })
    await click('View faces')
    expect(mounted.emitted('preview')).toBeUndefined()
    expect(mounted.emitted('assign')).toBeUndefined()
    expect(mounted.getComponent(RouterLinkStub).props('to')).toEqual(
      expect.objectContaining({ params: { personId: 'ada' } }),
    )
    await dismiss()
    await mounted.get('[aria-label="Assign to Ada Novak"]').trigger('click')
    expect(mounted.emitted('assign')).toHaveLength(1)
    await mounted.get('[aria-label="Preview Ada Novak on this page"]').trigger('click')
    expect(mounted.emitted('preview')).toHaveLength(1)
  })

  it('loads only when opened, scopes solely to the identity, and reuses cached crops', async () => {
    mocks.list.mockResolvedValue(
      batch(
        Array.from({ length: 6 }, (_, i) => face(`a${i}`)),
        'next',
        7,
      ),
    )
    const wrapper = setup()
    await flushPromises()
    expect(mocks.list).not.toHaveBeenCalled()
    await click('View faces')
    expect(mocks.list.mock.calls[0]![0].query).toEqual({
      'filter.entity_id': ['ada'],
      limit: 6,
      sort: 'detection_id',
      sort_direction: 'asc',
      cursor: null,
    })
    expect(wrapper.get('button').attributes('aria-expanded')).toBe('true')
    const dialog = document.getElementById(wrapper.get('button').attributes('aria-controls')!)!
    expect(dialog.getAttribute('role')).toBe('dialog')
    expect(dialog.getAttribute('aria-labelledby')).toBe(wrapper.get('button').attributes('id'))
    expect(document.querySelector('[role="dialog"] h4')).toBeNull()
    expect(document.body.textContent).not.toContain('6 of 7')
    expect(document.body.textContent).not.toContain('Load more faces')
    await dismiss()
    expect(wrapper.get('button').attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(wrapper.get('button').element)
    await click('View faces')
    expect(document.querySelector('[role="dialog"] h4')).toBeNull()
    expect(mocks.crop).toHaveBeenCalledTimes(6)
  })

  it('reports loading, list failure, retry and empty evidence', async () => {
    let reject!: (e: Error) => void
    mocks.list.mockImplementationOnce(
      () =>
        new Promise((_, fail) => {
          reject = fail
        }),
    )
    setup()
    await click('View faces')
    expect(document.body.textContent).toContain('Loading faces')
    reject(new Error('offline'))
    await flushPromises()
    expect(document.body.textContent).toContain('Could not load faces')
    await click('Retry')
    expect(document.body.textContent).toContain('No linked faces')
  })

  it('isolates late responses when the identity changes and refreshes invalidated membership', async () => {
    let finish!: (value: ReturnType<typeof batch>) => void
    mocks.list
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve
          }),
      )
      .mockResolvedValueOnce(batch([face('emil-1', 'emil')]))
    const wrapper = setup()
    await click('View faces')
    await wrapper.setProps({ personId: 'emil', name: 'Emil' })
    await click('View faces')
    finish(batch([face('ada-late')]))
    await flushPromises()
    expect(mocks.crop.mock.calls.map(([arg]) => arg.path.detection_id)).toEqual(['emil-1'])
    mocks.list.mockResolvedValue(batch([]))
    await client.invalidateQueries({ queryKey: queryKeys.faces.lists() })
    await flushPromises()
    expect(document.body.textContent).toContain('No linked faces')
  })

  it('opens on mouse hover without moving focus, closes on leave, and keeps clicked content open', async () => {
    const wrapper = setup()
    const trigger = wrapper.get('button')
    await trigger.trigger('pointerenter', { pointerType: 'mouse' })
    await new Promise((resolve) => setTimeout(resolve, 330))
    await flushPromises()
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(document.activeElement).not.toBe(document.querySelector('[role="dialog"]'))
    await trigger.trigger('pointerleave')
    await new Promise((resolve) => setTimeout(resolve, 280))
    await flushPromises()
    expect(trigger.attributes('aria-expanded')).toBe('false')
    await click('View faces')
    await trigger.trigger('pointerleave')
    await new Promise((resolve) => setTimeout(resolve, 280))
    await flushPromises()
    expect(trigger.attributes('aria-expanded')).toBe('true')
  })

  it('handles Escape within the gallery while stopping scan navigation shortcuts', async () => {
    const wrapper = setup()
    await click('View faces')
    const dialog = document.querySelector('[role="dialog"]')!
    const navigation = vi.fn()
    window.addEventListener('keydown', navigation)
    try {
      dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))
      expect(navigation).not.toHaveBeenCalled()
      dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
      await flushPromises()
      expect(wrapper.get('button').attributes('aria-expanded')).toBe('false')
      expect(document.activeElement).toBe(wrapper.get('button').element)
    } finally {
      window.removeEventListener('keydown', navigation)
    }
  })

  it('dismisses on the first outside pointer press after interacting with faces', async () => {
    mocks.list.mockResolvedValue(batch([face('a')]))
    const wrapper = setup()
    await click('View faces')
    const pointer = () => {
      const event = new Event('pointerdown', { bubbles: true })
      Object.defineProperty(event, 'pointerType', { value: 'mouse' })
      return event
    }
    document.querySelector('[role="list"]')!.dispatchEvent(pointer())
    await flushPromises()
    expect(wrapper.get('button').attributes('aria-expanded')).toBe('true')
    document.body.dispatchEvent(pointer())
    await flushPromises()
    expect(wrapper.get('button').attributes('aria-expanded')).toBe('false')
  })

  it('keeps other crops accessible when one authenticated crop fails', async () => {
    mocks.list.mockResolvedValue(batch([face('bad'), face('good')]))
    mocks.crop.mockRejectedValueOnce(new Error('missing media'))
    setup()
    await click('View faces')
    expect(document.querySelectorAll('[role="listitem"]')).toHaveLength(2)
    expect(document.body.textContent).toContain('crop unavailable')
    expect(mocks.crop).toHaveBeenCalledTimes(2)
  })
})
