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
    const badge = face.get('[data-face-status-badge]')
    expect(badge.attributes('data-slot')).toBe('badge')
    expect(badge.classes()).toContain('border-0')
    expect(badge.classes()).toContain('rounded-full')
    expect(badge.classes()).toContain('font-normal')
    expect(badge.classes()).toContain('shadow-xs')
    expect(badge.text()).toBe('Ada')
    expect(badge.get('span').classes()).toContain('truncate')
    expect(badge.get('svg').classes()).toContain('shrink-0')

    await wrapper.setProps({
      pageBounds: { left: 20, top: 40, width: 1000, height: 1600 },
    })

    expect(face.attributes('style')).toContain('left: 220px')
    expect(face.attributes('style')).toContain('width: 300px')
    expect(face.classes()).toContain('border-2')
    expect(face.get('[data-face-status-badge]').classes()).toContain('max-w-40')

    await face.trigger('click')
    expect(wrapper.emitted('selectFace')).toEqual([['face-identifier']])

    await wrapper.setProps({ showBadgeNames: false })
    expect(badge.find('span').exists()).toBe(false)
    expect(badge.find('svg').exists()).toBe(true)
    expect(badge.classes()).toContain('size-6')
  })

  it('stacks selected regions above unselected regions', async () => {
    const position = { left: 10, top: 10, width: 20, height: 20 }
    const wrapper = mount(DocumentPageOverlay, {
      props: {
        pageBounds: { left: 0, top: 0, width: 500, height: 800 },
        transcription: [
          { id: 'line-1', text: 'First line', position },
          { id: 'line-2', text: 'Second line', position },
        ],
        faces: [
          {
            id: 'face-1',
            personId: 'person-1',
            name: 'Ada',
            confidence: 98,
            status: 'assigned',
            position,
            portrait: '',
            portraitLoading: false,
          },
          {
            id: 'face-2',
            personId: null,
            name: 'Unknown',
            confidence: 90,
            status: 'unassigned',
            position,
            portrait: '',
            portraitLoading: false,
          },
        ],
        selectedLineIndex: 0,
        selectedFaceId: 'face-1',
        selectedPersonId: null,
        selectedCandidateFaceId: null,
      },
    })

    const lines = wrapper.findAll('[data-region-type="line"]')
    const faces = wrapper.findAll('[data-region-type="face"]')
    expect(lines[0]?.classes()).toContain('z-10')
    expect(lines[1]?.classes()).not.toContain('z-10')
    expect(faces[0]?.classes()).toContain('z-10')
    expect(faces[1]?.classes()).not.toContain('z-10')

    await wrapper.setProps({ selectedLineIndex: 1, selectedFaceId: 'face-2' })

    expect(lines[0]?.classes()).not.toContain('z-10')
    expect(lines[1]?.classes()).toContain('z-10')
    expect(faces[0]?.classes()).not.toContain('z-10')
    expect(faces[1]?.classes()).toContain('z-10')
  })
})
