import { mount, RouterLinkStub } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expect, it } from 'vitest'
import PersonNameTitle from '@/components/custom/PersonNameTitle.vue'

it('uses the person-card name style, linking a person with an arrow (#103)', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/?library=lib')
  const options = { global: { plugins: [router], stubs: { RouterLink: RouterLinkStub } } }
  const person = mount(PersonNameTitle, {
    props: { name: 'Hana Sidebar', personId: 'hana', query: { origin_matched_face: 'f' } },
    ...options,
  })
  expect(person.getComponent(RouterLinkStub).props('to')).toEqual({
    name: 'person-detail',
    params: { personId: 'hana' },
    // The source view's filters stay behind (#109).
    query: { origin_matched_face: 'f' },
  })
  expect(person.find('svg.lucide-chevron-right').exists()).toBe(true)
  // Only the name and arrow link, inside the heading rather than the whole line.
  const link = person.getComponent(RouterLinkStub)
  expect(link.element.parentElement!.tagName).toBe('H4')
  expect(link.text()).toBe('Hana Sidebar')
  expect(link.find('svg.lucide-chevron-right').exists()).toBe(true)
  const plain = mount(PersonNameTitle, { props: { name: 'Unlinked' }, ...options })
  expect(plain.findComponent(RouterLinkStub).exists()).toBe(false)
  expect(plain.find('svg').exists()).toBe(false)
  // Linked and plain names share the same title and heading styles.
  expect(plain.get('[data-slot="item-title"]').classes()).toEqual(
    person.get('[data-slot="item-title"]').classes(),
  )
  expect(plain.get('h4').classes()).toEqual(person.get('h4').classes())
  expect(plain.get('h4').text()).toBe('Unlinked')
})
