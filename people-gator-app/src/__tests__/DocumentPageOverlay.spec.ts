import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DocumentPageOverlay from '@/components/custom/DocumentPageOverlay.vue'

describe('DocumentPageOverlay', () => {
  it('uses transformed page bounds without scaling borders or badge content', async () => {
    const wrapper = mount(DocumentPageOverlay, {
      props: {
        pageBounds: { left: 10, top: 20, width: 500, height: 800 },
        transcription: [
          {
            id: 'line-1',
            text: 'A line',
            position: { left: 10, top: 5, width: 40, height: 10 },
          },
        ],
        faces: [
          {
            id: 'face-identifier',
            personId: 'person-1',
            name: 'Ada',
            confidence: 98,
            status: 'assigned',
            position: { left: 20, top: 25, width: 30, height: 15 },
            portrait: '',
            portraitLoading: false,
          },
        ],
        selectedLineIndex: 0,
        selectedFaceId: null,
        selectedPersonId: null,
        selectedCandidateFaceId: null,
      },
    })

    const face = wrapper.get('[data-region-type="face"]')
    expect(face.attributes('style')).toContain('left: 110px')
    expect(face.attributes('style')).toContain('top: 220px')
    expect(face.attributes('style')).toContain('width: 150px')
    expect(face.attributes('style')).toContain('height: 120px')
    expect(face.text()).not.toContain('face-identifier')
    expect(face.find('[data-face-status-badge] svg').exists()).toBe(true)
    expect(face.classes()).toContain('border-2')
    expect(face.get('[data-face-status-badge]').attributes('data-slot')).toBe('badge')
    expect(face.get('[data-face-status-badge]').classes()).toContain('size-5')

    await wrapper.setProps({
      pageBounds: { left: 20, top: 40, width: 1000, height: 1600 },
    })

    expect(face.attributes('style')).toContain('left: 220px')
    expect(face.attributes('style')).toContain('width: 300px')
    expect(face.classes()).toContain('border-2')
    expect(face.get('[data-face-status-badge]').classes()).toContain('size-5')

    await face.trigger('click')
    expect(wrapper.emitted('selectFace')).toEqual([['face-identifier']])
  })
})
