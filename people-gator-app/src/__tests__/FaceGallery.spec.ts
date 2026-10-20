import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import FaceGallery from '@/components/custom/FaceGallery.vue'
import type { Face } from '@/viewmodels/document-workspace.types'

const faces: Face[] = [
  {
    id: 'face-1',
    personId: 'person-1',
    name: 'A person with a deliberately long display name',
    wikidataId: 'Q7259',
    nlcrAuthorityId: 'xx0000000',
    confidence: 98,
    status: 'assigned',
    position: { left: 0, top: 0, width: 10, height: 10 },
    portrait: '',
    portraitLoading: false,
  },
  {
    id: 'face-2',
    personId: null,
    name: 'Unknown person',
    confidence: 87,
    status: 'unassigned',
    position: { left: 10, top: 10, width: 10, height: 10 },
    portrait: '',
    portraitLoading: false,
  },
]

describe('FaceGallery', () => {
  it('shows a compact status filter with counts and selectable thumbnails', async () => {
    const wrapper = mount(FaceGallery, {
      props: { faces, selectedFaceId: 'face-1' },
    })

    expect(wrapper.text()).toContain('Page faces')
    expect(wrapper.find('h2').exists()).toBe(false)
    expect(wrapper.text()).toContain('All2')
    expect(wrapper.text()).toContain('Annotated1')
    expect(wrapper.text()).toContain('Not annotated1')
    expect(wrapper.findAll('[aria-label^="Select face "]')).toHaveLength(2)
    expect(wrapper.find('[aria-label="Previous face"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Next face"]').exists()).toBe(false)
    expect(
      wrapper
        .get(
          '[aria-label="Select face 1: A person with a deliberately long display name, annotated, Unassigned"]',
        )
        .attributes('aria-pressed'),
    ).toBe('true')
    expect(wrapper.findAll('[data-face-status-badge]')).toHaveLength(2)
    expect(wrapper.get('[data-face-status-badge]').text()).toBe('')
    expect(wrapper.get('[data-face-status-badge]').attributes('title')).toBe('Unassigned')
    expect(wrapper.find('[data-face-status-badge] svg').exists()).toBe(true)
    expect(wrapper.get('[data-face-status-badge]').classes()).toContain('border-0')

    await wrapper.get('[aria-label="Select face 2: not annotated, Unassigned"]').trigger('click')
    expect(wrapper.emitted('select')).toContainEqual(['face-2'])
  })

  it('filters faces without clearing the current page selection', async () => {
    const wrapper = mount(FaceGallery, {
      props: { faces, selectedFaceId: 'face-1' },
    })

    await wrapper.get('[aria-label="Show not annotated faces"]').trigger('click')

    expect(wrapper.findAll('[aria-label^="Select face "]')).toHaveLength(1)
    expect(wrapper.find('[aria-label*="deliberately long display name"]').exists()).toBe(false)
    expect(
      wrapper.get('[aria-label="Select face 1: not annotated, Unassigned"]').attributes('aria-pressed'),
    ).toBe('false')
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('scrolls only the thumbnail viewport when navigation selects an offscreen face', async () => {
    const wrapper = mount(FaceGallery, { props: { faces, selectedFaceId: null } })
    const viewport = wrapper.get('[data-slot="scroll-area-viewport"]').element as HTMLElement
    const selected = wrapper.get('[aria-label^="Select face 2:"]').element as HTMLElement
    const scrollTo = vi.fn()
    viewport.scrollTo = scrollTo
    selected.scrollIntoView = vi.fn()
    vi.spyOn(viewport, 'getBoundingClientRect').mockReturnValue({ left: 0, right: 100, width: 100 } as DOMRect)
    vi.spyOn(selected, 'getBoundingClientRect').mockReturnValue({ left: 120, right: 180, width: 60 } as DOMRect)
    await wrapper.setProps({ selectedFaceId: 'face-2' })
    await wrapper.vm.$nextTick()
    expect(scrollTo).toHaveBeenCalledWith({ left: 100, behavior: 'smooth' })
    expect(selected.scrollIntoView).not.toHaveBeenCalled()
  })

  it('uses a useful empty-state label when the page has no faces', () => {
    const wrapper = mount(FaceGallery, {
      props: { faces: [], selectedFaceId: null },
    })

    expect(wrapper.get('[role="status"]').text()).toContain('No faces found')
  })
})
