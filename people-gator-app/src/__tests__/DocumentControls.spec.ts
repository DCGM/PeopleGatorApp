import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import DocumentControls from '@/components/custom/DocumentControls.vue'
import { useLinkStateFilter } from '@/composables/link-state-filter'

const props = {
  zoomPercent: 82,
  minimumZoomPercent: 55,
  maximumZoomPercent: 350,
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

  it('keeps only zoom, Names and link-state controls', async () => {
    const wrapper = mount(DocumentControls, { props })
    try {
      for (const [label, event, args] of [
        ['Zoom out', 'set-zoom', ['out']],
        ['Zoom in', 'set-zoom', ['in']],
        ['Center page', 'reset-view', []],
        ['Hide overlay badge names', 'toggle-badge-names', []],
      ] as const) {
        await wrapper.get(`button[aria-label="${label}"]`).trigger('click')
        expect(wrapper.emitted(event)?.slice(-1)[0]).toEqual(args)
      }
      for (const label of ['Previous line', 'Next line', 'Previous face', 'Next face'])
        expect(wrapper.find(`button[aria-label="${label}"]`).exists()).toBe(false)
      expect(wrapper.find('[aria-label="Translation"]').exists()).toBe(false)
      await wrapper.setProps({ zoomPercent: 55 })
      expect(wrapper.get('button[aria-label="Zoom out"]').attributes('disabled')).toBeDefined()
    } finally {
      wrapper.unmount()
    }
  })
})
