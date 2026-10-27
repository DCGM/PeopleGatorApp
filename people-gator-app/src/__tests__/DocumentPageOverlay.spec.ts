import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { h } from 'vue'
import UiTooltip from '@/components/custom/UiTooltip.vue'
import DocumentPageOverlay from '@/components/custom/DocumentPageOverlay.vue'
import type { TranscriptionEntitySpan } from '@/viewmodels/document-workspace.types'

describe('DocumentPageOverlay', () => {
  it('highlights every linked mention by identity and gives the current line precedence', async () => {
    const position = { left: 10, top: 10, width: 20, height: 5 }
    const span = (entity_id?: string): TranscriptionEntitySpan => ({
      entity_id,
      label: 'person',
      text: 'Ada',
      line_id: 'line',
      start_index: 0,
      end_index: 3,
    })
    const wrapper = mount(DocumentPageOverlay, {
      props: {
        pageBounds: { left: 0, top: 0, width: 500, height: 800 },
        transcription: [
          { id: 'selected', text: 'Ada', position, entities: [span('person-1')] },
          { id: 'mention-1', text: 'Ada', position, entities: [span('person-1')] },
          { id: 'mention-2', text: 'Ada', position, entities: [span('person-2'), span('person-1')] },
          { id: 'other-person', text: 'Ada', position, entities: [span('person-2')] },
          { id: 'unlinked', text: 'Ada', position, entities: [span()] },
          { id: 'no-spans', text: 'Ada', position },
          { id: 'empty-spans', text: 'Ada', position, entities: [] },
        ],
        faces: [],
        selectedLineIndex: 0,
        selectedFaceId: null,
        selectedPersonId: 'person-1',
        selectedCandidateFaceId: null,
      },
    })
    const lines = wrapper.findAll('[data-region-type="line"]')
    expect(lines[0]!.classes()).toContain('border-accent')
    expect(lines[0]!.classes()).not.toContain('border-orange-500')
    // The current line is also a mention, so it keeps the accent with an orange ring.
    expect(lines[0]!.classes()).toContain('ring-orange-500')
    expect(lines[0]!.attributes('aria-label')).toBe(
      'Select line 1: Ada (mentions the selected person)',
    )
    for (const line of lines.slice(1, 3)) {
      expect(line.classes()).toContain('border-orange-500')
      expect(line.classes()).toContain('bg-orange-500/15')
      expect(line.classes()).toContain('hover:bg-orange-500/30')
      expect(line.attributes('aria-label')).toMatch(/\(mentions the selected person\)$/)
      expect(line.attributes('aria-pressed')).toBe('false')
    }
    for (const [offset, line] of lines.slice(3).entries()) {
      expect(line.classes()).toContain('border-transparent')
      expect(line.classes()).toContain('hover:border-accent/70')
      expect(line.classes()).not.toContain('border-orange-500')
      expect(line.attributes('aria-label')).toBe(`Select line ${offset + 4}: Ada`)
    }

    await lines[1]!.trigger('click')
    expect(wrapper.emitted('selectLine')).toEqual([[1]])
    await wrapper.setProps({ selectedLineIndex: 1 })
    expect(lines[0]!.classes()).toContain('border-orange-500')
    expect(lines[1]!.classes()).toContain('border-accent')
    expect(lines[1]!.classes()).not.toContain('border-orange-500')
    expect(lines[1]!.classes()).toContain('ring-orange-500')
    expect(lines[1]!.attributes('aria-pressed')).toBe('true')

    await wrapper.setProps({ selectedPersonId: 'person-2' })
    expect(lines[0]!.classes()).toContain('border-transparent')
    expect(lines[1]!.classes()).toContain('border-accent')
    expect(lines[1]!.classes()).not.toContain('ring-orange-500')
    expect(lines[1]!.attributes('aria-label')).toBe('Select line 2: Ada')
    expect(lines[2]!.classes()).toContain('border-orange-500')
    expect(lines[3]!.classes()).toContain('border-orange-500')

    await wrapper.setProps({ selectedPersonId: null })
    for (const [index, line] of lines.entries()) {
      expect(line.classes()).toContain(index === 1 ? 'border-accent' : 'border-transparent')
      expect(line.classes()).not.toContain('border-orange-500')
      expect(line.classes()).not.toContain('ring-orange-500')
      expect(line.attributes('aria-label')).not.toContain('mentions')
    }
  })

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

    expect(wrapper.findComponent(UiTooltip).exists()).toBe(false)
    expect(wrapper.find('[title]').exists()).toBe(false)
    const face = wrapper.get('[data-region-type="face"]')
    expect(face.attributes('aria-label')).toContain('Select Ada:')
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


it('opens actions from a detection, closes with Escape and returns keyboard focus', async () => {
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
  const wrapper = mount(DocumentPageOverlay, {
    attachTo: document.body,
    props: {
      pageBounds: { left: 0, top: 0, width: 500, height: 800 }, transcription: [],
      faces: [{ id: 'one', personId: null, name: 'Unknown', confidence: 99, status: 'unassigned',
        position: { left: 10, top: 10, width: 20, height: 20 }, portrait: '', portraitLoading: false }],
      selectedLineIndex: 0, selectedFaceId: null, selectedPersonId: null, selectedCandidateFaceId: null,
    },
    slots: { actions: () => h('button', { type: 'button' }, 'Link') },
  })
  try {
    const detection = wrapper.get('[data-region-type="face"]')
    await detection.trigger('click')
    await wrapper.setProps({ selectedFaceId: 'one' })
    await flushPromises()
    const panel = document.querySelector<HTMLElement>('[data-slot="popover-content"]')
    expect(panel).not.toBeNull()
    expect(wrapper.emitted('selectFace')).toEqual([['one']])
    expect(panel!.contains(document.activeElement)).toBe(true)
    panel!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    await new Promise(resolve => setTimeout(resolve, 10))
    expect(document.querySelector('[data-slot="popover-content"]')).toBeNull()
    expect(document.activeElement).toBe(detection.element)
  } finally {
    wrapper.unmount()
    vi.unstubAllGlobals()
  }
})
