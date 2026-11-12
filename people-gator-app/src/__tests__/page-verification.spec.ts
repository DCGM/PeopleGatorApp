import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import PageVerification from '@/components/custom/PageVerification.vue'
import PageReviewControls from '@/components/custom/PageReviewControls.vue'
import VerificationProgress from '@/components/custom/VerificationProgress.vue'
import { verificationProgress } from '@/lib/verification'
import type { PageResponse } from '@/client'

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  allowed: { value: true },
  pages: [] as unknown[],
}))
vi.mock('@/query/media', async () => {
  const { ref: vueRef } = await import('vue')
  return {
    usePagePatchMutation: () => ({
      mutate: mocks.mutate,
      isPending: vueRef(false),
      isError: vueRef(false),
    }),
    usePageListQuery: () => ({
      data: vueRef({ pages: [{ items: mocks.pages }] }),
      hasNextPage: vueRef(false),
      isFetching: vueRef(false),
      isError: vueRef(false),
      fetchNextPage: vi.fn(),
    }),
  }
})
vi.mock('@/query/people-filter-options', () => ({
  usePeopleFilterOptions: () => ({ labels: ref({ reviewer: 'Rita Reviewer' }) }),
}))
vi.mock('@/composables/can-annotate', () => ({
  useCanAnnotate: () => computed(() => mocks.allowed.value),
}))

const page = (id: string, extra: Partial<PageResponse> = {}) =>
  ({
    source_id: `source-${id}`,
    library: 'lib',
    document_id: 'doc',
    page_id: id,
    verification_state: 'not_verified',
    ...extra,
  }) as PageResponse

async function mountControls(current: PageResponse) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/libraries/:libraryId/documents/:documentId/pages/:pageId',
        name: 'document-page',
        component: defineComponent(() => () => null),
      },
    ],
  })
  await router.push({
    name: 'document-page',
    params: { libraryId: 'lib', documentId: 'doc', pageId: current.page_id },
    query: { panel: 'info', gallery_not_verified: 'on', person: 'face', pages_view: 'expanded' },
  })
  const wrapper = mount(PageReviewControls, {
    props: { page: current },
    attachTo: window.document.body,
    global: { plugins: [router] },
  })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  mocks.allowed.value = true
  window.document.body.innerHTML = ''
})

describe('page verification (#149)', () => {
  it('shows the page state as a label with its verifier', async () => {
    const wrapper = mount(PageVerification, { props: { page: page('a') } })
    expect(wrapper.get('[data-verification-badge]').text()).toBe('Not verified')
    expect(wrapper.find('button').exists()).toBe(false)
    await wrapper.setProps({
      page: page('a', {
        verification_state: 'verified',
        verified_by_user_id: 'reviewer',
        verified_at: new Date(Date.now() - 600_000).toISOString(),
      }),
    })
    expect(wrapper.get('[data-verification-badge]').attributes('data-state')).toBe('verified')
    expect(wrapper.text()).toMatch(/Rita Reviewer · \d+ min ago/)
  })

  it('draws document progress as a ring with the verified count', () => {
    expect(verificationProgress(1, 4)).toBe(0.25)
    expect(verificationProgress(3, 0)).toBe(0)
    expect(verificationProgress(null, 3)).toBe(0)
    const ring = mount(VerificationProgress, { props: { verified: 1, total: 3 } })
    expect(ring.text()).toBe('1/3')
    expect(ring.get('[role="img"]').attributes('aria-label')).toBe('1 of 3 pages verified')
    expect(ring.findAll('circle')).toHaveLength(2)
    const empty = mount(VerificationProgress, { props: { verified: 0, total: 2 } })
    expect(empty.findAll('circle')).toHaveLength(1)
    expect(mount(VerificationProgress).text()).toBe('–/–')
  })

  it('verifies from the viewer controls and preserves the expanded gallery across page navigation', async () => {
    mocks.pages = [page('a'), page('b'), page('c')]
    const wrapper = await mountControls(page('b'))
    await wrapper.get('button[aria-label="Verify page"]').trigger('click')
    expect(mocks.mutate).toHaveBeenLastCalledWith({
      sourceId: 'source-b',
      payload: { verification_state: 'verified' },
    })
    expect(wrapper.get('a[aria-label="Previous page"]').attributes('href')).toBe(
      '/libraries/lib/documents/doc/pages/a?gallery_not_verified=on&pages_view=expanded&panel=info',
    )
    expect(wrapper.get('a[aria-label="Next page"]').attributes('href')).toBe(
      '/libraries/lib/documents/doc/pages/c?gallery_not_verified=on&pages_view=expanded&panel=info',
    )
    wrapper.unmount()
  })

  it('removes verification from the verified button menu; edges disable navigation', async () => {
    mocks.pages = [page('a'), page('b')]
    const wrapper = await mountControls(
      page('b', { verification_state: 'verified', verified_by_user_id: 'reviewer' }),
    )
    const trigger = wrapper.get('button[aria-label="Page verified, options"]')
    expect(trigger.classes()).toContain('bg-emerald-600')
    await trigger.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(window.document.body.textContent).toContain('Rita Reviewer')
    const remove = [
      ...window.document.body.querySelectorAll<HTMLElement>('[role="menuitem"]'),
    ].find((item) => item.textContent?.includes('Remove verification'))!
    remove.click()
    await flushPromises()
    expect(mocks.mutate).toHaveBeenLastCalledWith({
      sourceId: 'source-b',
      payload: { verification_state: 'not_verified' },
    })
    expect(wrapper.get('button[aria-label="Next page"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('a[aria-label="Previous page"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows only the state for read-only users', async () => {
    mocks.allowed.value = false
    mocks.pages = [page('a')]
    const wrapper = await mountControls(page('a'))
    expect(wrapper.find('[data-page-verify]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Page not verified"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
