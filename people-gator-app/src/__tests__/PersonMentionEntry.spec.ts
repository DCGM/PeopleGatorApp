import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { expect, it } from 'vitest'
import PersonMentionEntry from '@/components/custom/PersonMentionEntry.vue'
import AnnotationLastChange from '@/components/custom/AnnotationLastChange.vue'
import type { PersonMention } from '@/viewmodels/person-detail.types'
it('uses the shared last-change popover and orange underlined sans serif mention text', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  const wrapper = mount(PersonMentionEntry, {
    props: {
      personId: 'person',
      linkStates: [],
      mention: {
        id: 'm1',
        excerpt: 'Signed by Ada yesterday.',
        matchedText: 'Ada',
        library: 'NDK',
        documentTitle: 'Letters',
        documentId: 'doc',
        pageId: 'p1',
        pageLabel: 'p1',
        metadata: { last_touched_at: '2026-10-29T08:00:00Z', last_touched_by_user_id: 'reviewer' },
      } as PersonMention,
    },
    global: {
      plugins: [router],
      stubs: { RouterLink: RouterLinkStub, AnnotationLastChange: true },
    },
  })
  expect(wrapper.classes()).toContain('font-sans')
  expect(wrapper.get('mark').text()).toBe('Ada')
  expect(wrapper.get('mark').classes()).toEqual(
    expect.arrayContaining(['bg-transparent', 'text-secondary', 'underline']),
  )
  expect(wrapper.findComponent(RouterLinkStub).text()).toContain('NDK · Letters')
  const trigger = wrapper.get('button[aria-label="Details for mention m1"]')
  expect(trigger.find('svg.lucide-info').exists()).toBe(true)
  await trigger.trigger('mouseenter')
  await flushPromises()
  expect(wrapper.findComponent(AnnotationLastChange).props()).toMatchObject({
    touchedAt: '2026-10-29T08:00:00Z',
    userId: 'reviewer',
  })
  expect(wrapper.text()).not.toContain('Creation / import')
  wrapper.unmount()
})
