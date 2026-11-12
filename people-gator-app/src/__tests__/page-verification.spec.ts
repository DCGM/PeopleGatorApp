import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import PageVerification from '@/components/custom/PageVerification.vue'
import type { PageResponse } from '@/client'

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  allowed: { value: true },
  error: { value: false },
}))
vi.mock('@/query/media', () => ({
  usePagePatchMutation: () => ({
    mutate: mocks.mutate,
    isPending: ref(false),
    isError: ref(mocks.error.value),
  }),
}))
vi.mock('@/query/people-filter-options', () => ({
  usePeopleFilterOptions: () => ({ labels: ref({ reviewer: 'Rita Reviewer' }) }),
}))
vi.mock('@/composables/can-annotate', () => ({ useCanAnnotate: () => ref(mocks.allowed.value) }))

const page = { source_id: 'source', verification_state: 'not_verified' } as PageResponse

describe('page verification (#149)', () => {
  it('verifies a page and removes its verification', async () => {
    const wrapper = mount(PageVerification, { props: { page } })
    expect(wrapper.text()).toContain('Page not verified')
    await wrapper.get('button').trigger('click')
    expect(mocks.mutate).toHaveBeenLastCalledWith({
      sourceId: 'source',
      payload: { verification_state: 'verified' },
    })
    await wrapper.setProps({
      page: {
        ...page,
        verification_state: 'verified',
        verified_by_user_id: 'reviewer',
        verified_at: new Date(Date.now() - 600_000).toISOString(),
      },
    })
    expect(wrapper.text()).toContain('Page verified')
    expect(wrapper.text()).toMatch(/Rita Reviewer · \d+ min ago/)
    expect(wrapper.get('button').text()).toBe('Remove verification')
    await wrapper.get('button').trigger('click')
    expect(mocks.mutate).toHaveBeenLastCalledWith({
      sourceId: 'source',
      payload: { verification_state: 'not_verified' },
    })
  })

  it('shows the state without an action for read-only users', () => {
    mocks.allowed.value = false
    const wrapper = mount(PageVerification, { props: { page } })
    expect(wrapper.text()).toContain('Page not verified')
    expect(wrapper.find('button').exists()).toBe(false)
    mocks.allowed.value = true
  })

  it('reports a failed save', () => {
    mocks.error.value = true
    const wrapper = mount(PageVerification, { props: { page } })
    expect(wrapper.get('[role=alert]').text()).toBe('Could not save verification.')
    mocks.error.value = false
  })
})
