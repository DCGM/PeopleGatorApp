import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import LoadableImage from '@/components/custom/LoadableImage.vue'

describe('LoadableImage', () => {
  it('shows a skeleton while the image request is pending before a URL exists', async () => {
    const wrapper = mount(LoadableImage, {
      props: { alt: 'Scan', loading: true },
      slots: { fallback: '<span>Image unavailable</span>' },
    })

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('[data-slot="image-skeleton"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Image unavailable')

    await wrapper.setProps({ loading: false })

    expect(wrapper.find('[data-slot="image-skeleton"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Image unavailable')
  })

  it('shows a skeleton until the image loads and resets when its source changes', async () => {
    const wrapper = mount(LoadableImage, {
      props: { src: '/first.jpg', alt: 'Portrait' },
    })

    expect(wrapper.get('[data-slot="loadable-image"]').attributes('aria-busy')).toBe('true')
    expect(wrapper.find('[data-slot="image-skeleton"]').exists()).toBe(true)
    expect(wrapper.get('img').classes()).toContain('opacity-0')

    await wrapper.get('img').trigger('load')

    expect(wrapper.get('[data-slot="loadable-image"]').attributes('aria-busy')).toBe('false')
    expect(wrapper.find('[data-slot="image-skeleton"]').exists()).toBe(false)
    expect(wrapper.get('img').classes()).toContain('opacity-100')

    await wrapper.setProps({ src: '/second.jpg' })

    expect(wrapper.get('[data-slot="loadable-image"]').attributes('aria-busy')).toBe('true')
    expect(wrapper.find('[data-slot="image-skeleton"]').exists()).toBe(true)
  })

  it('removes the skeleton and renders its fallback when loading fails', async () => {
    const wrapper = mount(LoadableImage, {
      props: { src: '/missing.jpg', alt: 'Missing scan' },
      slots: { fallback: '<span>Image unavailable</span>' },
    })

    await wrapper.get('img').trigger('error')

    expect(wrapper.find('[data-slot="image-skeleton"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Image unavailable')
  })
})
