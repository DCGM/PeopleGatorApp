import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { h } from 'vue'
import UiTooltip from '@/components/custom/UiTooltip.vue'
import DocumentPageOverlay from '@/components/custom/DocumentPageOverlay.vue'
import { HOVER_CARD_CLOSE_DELAY, HOVER_CARD_OPEN_DELAY } from '@/composables/hover-card'
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
          {
            id: 'mention-2',
            text: 'Ada',
            position,
            entities: [span('person-2'), span('person-1')],
          },
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

  it('marks every line of the selected name mentions as selected (#176)', () => {
    const position = { left: 10, top: 10, width: 20, height: 5 }
    const wrapper = mount(DocumentPageOverlay, {
      props: {
        pageBounds: { left: 0, top: 0, width: 500, height: 800 },
        transcription: ['a', 'b', 'c', 'd'].map((id) => ({ id, text: id, position })),
        faces: [],
        selectedLineIndex: 0,
        selectedFaceId: null,
        selectedPersonId: null,
        selectedCandidateFaceId: null,
        selectedMentionLines: [1, 3],
      },
    })
    const lines = wrapper.findAll('[data-region-type="line"]')
    expect(lines.map((line) => line.attributes('aria-pressed'))).toEqual([
      'true',
      'true',
      'false',
      'true',
    ])
    expect(lines[3]!.classes()).toContain('border-accent')
    expect(lines[2]!.classes()).toContain('border-transparent')
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

    // A selected face is accent like a selected line; its selected person adds the orange ring.
    await wrapper.setProps({ selectedFaceId: 'face-identifier' })
    expect(face.classes()).toEqual(expect.arrayContaining(['border-accent', 'bg-accent/20']))
    expect(face.classes()).not.toContain('ring-orange-500')
    await wrapper.setProps({ selectedPersonId: 'person-1' })
    expect(face.classes()).toEqual(
      expect.arrayContaining(['border-accent', 'bg-accent/20', 'ring-orange-500']),
    )
    // Another face of the selected person is orange like a mention of that person.
    await wrapper.setProps({ selectedFaceId: null })
    expect(face.classes()).toEqual(
      expect.arrayContaining(['border-orange-500', 'bg-orange-500/15']),
    )
    await wrapper.setProps({ selectedPersonId: null })

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

it('expands the selected tag into one card through viewport movement and collapses it on an outside scan click, not a drag', async () => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
  const detectionFace = (id: string, width = 20) => ({
    id,
    personId: null,
    name: 'Unknown',
    confidence: 99,
    status: 'unassigned' as const,
    position: { left: 10, top: 10, width, height: 20 },
    portrait: '',
    portraitLoading: false,
  })
  const wrapper = mount(DocumentPageOverlay, {
    attachTo: document.body,
    props: {
      pageBounds: { left: 0, top: 0, width: 500, height: 800 },
      transcription: [],
      faces: [detectionFace('one'), detectionFace('two'), detectionFace('hidden', 0)],
      selectedLineIndex: 0,
      selectedFaceId: null,
      selectedPersonId: null,
      selectedCandidateFaceId: null,
    },
    slots: { card: () => h('button', { type: 'button' }, 'Link') },
  })
  const panel = () => document.querySelector<HTMLElement>('[data-slot="popover-content"]')
  const settle = async () => {
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 10))
  }
  const press = (target: EventTarget, type: string, clientX = 0) =>
    target.dispatchEvent(new MouseEvent(type, { bubbles: true, clientX, clientY: 0 }))
  try {
    const detection = wrapper.get('[data-detection-id="one"]')
    ;(detection.element as HTMLElement).focus()
    await detection.trigger('click')
    await wrapper.setProps({ selectedFaceId: 'one' })
    await settle()
    expect(panel()).not.toBeNull()
    expect(wrapper.emitted('selectFace')).toEqual([['one']])
    // The panel itself takes focus, so no action tooltip pops up on open.
    expect(document.activeElement).toBe(panel())
    expect(panel()!.getAttribute('aria-label')).toBe('Details for unassigned face')
    // The card replaces the selected face's name tag; other tags stay.
    const tag = (id: string) => wrapper.get(`[data-detection-id="${id}"] > *`)
    expect((tag('one').element as HTMLElement).style.display).toBe('none')
    expect((tag('two').element as HTMLElement).style.display).toBe('')
    panel()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(wrapper.emitted('clearFace')).toEqual([[]])
    await wrapper.setProps({ selectedFaceId: null })
    await settle()
    expect(panel()).toBeNull()
    expect(document.activeElement).toBe(detection.element)

    // Keyboard shortcuts, the toolbar and the gallery select without moving focus.
    ;(document.activeElement as HTMLElement).blur()
    await wrapper.setProps({ selectedFaceId: 'two' })
    await settle()
    expect(panel()).not.toBeNull()
    expect(panel()!.contains(document.activeElement)).toBe(false)

    await detection.trigger('click')
    await wrapper.setProps({ selectedFaceId: 'one' })
    await settle()
    const reopened = panel()!
    press(reopened.querySelector('button')!, 'pointerdown')
    press(reopened.querySelector('button')!, 'pointerup')
    await flushPromises()
    expect(panel()).toBe(reopened)
    // Dragging the scan keeps the actions; viewport movement keeps them too.
    press(document.body, 'pointerdown', 10)
    press(window, 'pointerup', 60)
    await settle()
    expect(panel()).toBe(reopened)
    // A press on a box reaches the scan, so a drag from it pans and keeps the actions too.
    const reachedScan = vi.fn()
    document.body.addEventListener('pointerdown', reachedScan, { once: true })
    press(detection.element, 'pointerdown', 10)
    press(window, 'pointerup', 60)
    await settle()
    expect(reachedScan).toHaveBeenCalledTimes(1)
    expect(panel()).toBe(reopened)
    await wrapper.setProps({ pageBounds: { left: -900, top: -800, width: 1000, height: 1600 } })
    expect(panel()).toBe(reopened)
    // A click off the face unselects it; its actions close at once.
    press(document.body, 'pointerdown', 10)
    press(window, 'pointerup', 12)
    await settle()
    expect(panel()).toBeNull()
    expect(wrapper.emitted('clearFace')).toHaveLength(2)
    await wrapper.setProps({ selectedFaceId: null })
    expect(detection.attributes('aria-pressed')).toBe('false')
    await detection.trigger('click')
    await wrapper.setProps({ selectedFaceId: 'one' })
    await settle()
    expect(panel()).not.toBeNull()

    // A click on a face box only selects: the selected one stays, another one takes over.
    for (const id of ['one', 'two']) {
      const box = wrapper.get(`[data-detection-id="${id}"]`)
      press(box.element, 'pointerdown', 10)
      press(window, 'pointerup', 10)
      await box.trigger('click')
      await settle()
      expect(wrapper.emitted('clearFace')).toHaveLength(2)
      expect(wrapper.emitted('selectFace')!.slice(-1)).toEqual([[id]])
    }
    expect(panel()).not.toBeNull()

    // A touch drag sends no click, so a later click on the toolbar must not report it.
    const touch = (target: EventTarget, type: string) => {
      const event = new MouseEvent(type, { bubbles: true })
      Object.defineProperty(event, 'pointerType', { value: 'touch' })
      target.dispatchEvent(event)
    }
    const toolbar = document.body.appendChild(document.createElement('button'))
    toolbar.addEventListener('pointerdown', (event) => event.stopPropagation())
    touch(detection.element, 'pointerdown')
    touch(toolbar, 'pointerdown')
    toolbar.click()
    await settle()
    expect(panel()).not.toBeNull()
    expect(wrapper.emitted('clearFace')).toHaveLength(2)
    // A tap off the face still unselects it.
    touch(document.body, 'pointerdown')
    document.body.click()
    await settle()
    expect(panel()).toBeNull()
    expect(wrapper.emitted('clearFace')).toHaveLength(3)
    toolbar.remove()
    await wrapper.setProps({ selectedFaceId: null })
    await detection.trigger('click')
    await wrapper.setProps({ selectedFaceId: 'one' })
    await settle()
    expect(panel()).not.toBeNull()

    // Escape on the selected box clears the selection in one press.
    await detection.trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('clearFace')).toHaveLength(4)

    // Selecting another face collapses the previous card to its tag.
    await wrapper.setProps({ selectedFaceId: 'two' })
    await settle()
    expect(document.querySelectorAll('[data-slot="popover-content"]')).toHaveLength(1)
    expect(panel()!.getAttribute('data-detection-card')).toBe('two')
    expect((tag('one').element as HTMLElement).style.display).toBe('')

    // A face without a drawable box never gets an unanchored panel.
    await wrapper.setProps({ selectedFaceId: 'hidden' })
    await settle()
    expect(panel()).toBeNull()

    // Hovering a face opens its full card without selecting it or moving focus (#203).
    await wrapper.setProps({ selectedFaceId: 'two' })
    await settle()
    const selections = wrapper.emitted('selectFace')!.length
    const rest = (delay: number) => new Promise((resolve) => setTimeout(resolve, delay + 20))
    ;(detection.element as HTMLElement).focus()
    await detection.trigger('mouseenter')
    await rest(HOVER_CARD_OPEN_DELAY)
    await settle()
    expect(document.querySelectorAll('[data-slot="popover-content"]')).toHaveLength(1)
    expect(panel()!.getAttribute('data-detection-card')).toBe('one')
    expect(document.activeElement).toBe(detection.element)
    expect(wrapper.emitted('selectFace')).toHaveLength(selections)
    // Left unused, it closes and the selected face's card returns.
    await detection.trigger('mouseleave')
    await rest(HOVER_CARD_CLOSE_DELAY)
    await settle()
    expect(panel()!.getAttribute('data-detection-card')).toBe('two')
    expect(document.activeElement).toBe(detection.element)
    // Escape cancels a hovered card and keeps the selection.
    const cleared = wrapper.emitted('clearFace')!.length
    await detection.trigger('mouseenter')
    await rest(HOVER_CARD_OPEN_DELAY)
    await settle()
    expect(panel()!.getAttribute('data-detection-card')).toBe('one')
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await settle()
    expect(panel()!.getAttribute('data-detection-card')).toBe('two')
    expect(wrapper.emitted('clearFace')).toHaveLength(cleared)
    await detection.trigger('mouseleave')
    // The pointer may travel into the card; using the card selects its face.
    await detection.trigger('mouseenter')
    await rest(HOVER_CARD_OPEN_DELAY)
    await settle()
    await detection.trigger('mouseleave')
    panel()!.dispatchEvent(new MouseEvent('mouseenter'))
    await rest(HOVER_CARD_CLOSE_DELAY)
    expect(panel()!.getAttribute('data-detection-card')).toBe('one')
    press(panel()!.querySelector('button')!, 'pointerdown')
    expect(wrapper.emitted('selectFace')!.slice(selections)).toEqual([['one']])
    await wrapper.setProps({ selectedFaceId: 'one' })
    panel()!.dispatchEvent(new MouseEvent('mouseleave'))
    await rest(HOVER_CARD_CLOSE_DELAY)
    await settle()
    expect(panel()!.getAttribute('data-detection-card')).toBe('one')
  } finally {
    wrapper.unmount()
    vi.unstubAllGlobals()
  }
})
