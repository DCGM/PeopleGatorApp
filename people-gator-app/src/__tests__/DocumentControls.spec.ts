import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import DocumentControls from '@/components/custom/DocumentControls.vue'
import { useLinkStateFilter } from '@/composables/link-state-filter'

const props = {
  selectedLineIndex: 1,
  lineCount: 3,
  selectedFaceIndex: 1,
  faceCount: 3,
  zoomPercent: 82,
  minimumZoomPercent: 55,
  maximumZoomPercent: 350,
  translationOptions: ['off', 'cs', 'en', 'de'] as const,
  isTranslationOpen: false,
  selectedLanguage: 'en' as const,
  showBadgeNames: true,
}

describe('scan toolbar', () => {
  it('keeps inline selections and reset synchronized with direct URLs and history', async () => {
    const harness = defineComponent({
      setup() {
        const states = useLinkStateFilter()
        return () =>
          h(DocumentControls, {
            ...props,
            linkStates: states.value,
            'onUpdate:linkStates': (value) => {
              states.value = value
            },
          })
      },
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/scan/:id', component: harness }],
    })
    await router.push('/scan/1?line=L4&translate=on&link_state=verified')
    const wrapper = mount(harness, { global: { plugins: [router] } })
    const state = (name: string) => wrapper.get(`button[aria-label="${name}"]`)
    const all = () => wrapper.findAll('button').find((button) => button.text() === 'All')!
    const expectSelection = (labels: string[]) => {
      for (const label of ['Automatic', 'Manual', 'Verified']) {
        expect(state(label).attributes('aria-pressed')).toBe(String(labels.includes(label)))
        // Tooltip triggers must not overwrite the state used by standard
        // ToggleGroup styling with their own open/closed state.
        expect(state(label).attributes('data-state')).toBe(labels.includes(label) ? 'on' : 'off')
      }
      expect(all().attributes('aria-pressed')).toBe(String(labels.length === 0))
      expect(wrapper.find('[role="combobox"]').exists()).toBe(false)
      expect(wrapper.find('[data-slot="badge"]').exists()).toBe(false)
      expect(wrapper.find('[aria-label="Show filters"]').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('Clear all filters')
    }
    try {
      expect(wrapper.get('[role="toolbar"]').attributes('aria-label')).toBe('Scan tools')
      expect(wrapper.get('[data-slot="toggle-group"]').attributes('aria-label')).toBe('Link state')
      expectSelection(['Verified'])
      await state('Automatic').trigger('click')
      await flushPromises()
      expectSelection(['Automatic', 'Verified'])
      expect(router.currentRoute.value.query.link_state).toEqual(['automatic', 'verified'])
      await state('Manual').trigger('click')
      await flushPromises()
      expectSelection(['Automatic', 'Manual', 'Verified'])
      expect(router.currentRoute.value.query.link_state).toEqual([
        'automatic',
        'manual',
        'verified',
      ])
      await state('Automatic').trigger('click')
      await flushPromises()
      expectSelection(['Manual', 'Verified'])
      await all().trigger('click')
      await flushPromises()
      expectSelection([])
      expect(router.currentRoute.value.query).toEqual({ line: 'L4', translate: 'on' })
      router.back()
      await flushPromises()
      expectSelection(['Manual', 'Verified'])
      router.forward()
      await flushPromises()
      expectSelection([])
      // A fresh mount reads the URL rather than retaining component-local state.
      await router.push('/scan/1?link_state=manual&link_state=verified')
      const reloaded = mount(harness, { global: { plugins: [router] } })
      try {
        expect(reloaded.get('button[aria-label="Manual"]').attributes('aria-pressed')).toBe('true')
        expect(reloaded.get('button[aria-label="Verified"]').attributes('aria-pressed')).toBe(
          'true',
        )
        expect(reloaded.get('button[aria-label="Automatic"]').attributes('aria-pressed')).toBe(
          'false',
        )
      } finally {
        reloaded.unmount()
      }
    } finally {
      wrapper.unmount()
    }
  })

  it('retains navigation, zoom, Names and translation actions alongside the toggles', async () => {
    const wrapper = mount(DocumentControls, { props })
    try {
      for (const [label, event, args] of [
        ['Previous line', 'previous-line', []],
        ['Next line', 'next-line', []],
        ['Previous face', 'previous-face', []],
        ['Next face', 'next-face', []],
        ['Zoom out', 'set-zoom', ['out']],
        ['Zoom in', 'set-zoom', ['in']],
        ['Center page', 'reset-view', []],
        ['Hide overlay badge names', 'toggle-badge-names', []],
      ] as const) {
        await wrapper.get(`button[aria-label="${label}"]`).trigger('click')
        expect(wrapper.emitted(event)?.slice(-1)[0]).toEqual(args)
      }
      const translation = wrapper.get('[aria-label="Translation"]')
      await translation.findAll('button')[2]!.trigger('click')
      expect(wrapper.emitted('select-translation')).toEqual([['en']])
      await wrapper.setProps({ selectedLineIndex: 0, selectedFaceIndex: 0, zoomPercent: 55 })
      for (const label of ['Previous line', 'Previous face', 'Zoom out'])
        expect(wrapper.get(`button[aria-label="${label}"]`).attributes('disabled')).toBeDefined()
    } finally {
      wrapper.unmount()
    }
  })
})
