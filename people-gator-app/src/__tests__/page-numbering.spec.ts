import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { pagePosition } from '@/lib/page-position'
import { pageGalleryLabel } from '@/viewmodels/document-page-gallery'
import PageNumberEditor from '@/components/custom/PageNumberEditor.vue'
import DocumentCard from '@/components/custom/DocumentCard.vue'
import type { PageResponse } from '@/client'

const mocks = vi.hoisted(() => ({ mutate: vi.fn() }))
vi.mock('@/query/media', () => ({
  usePageNumberMutation: () => ({
    mutate: mocks.mutate,
    isPending: ref(false),
    isError: ref(false),
  }),
}))
vi.mock('@/composables/can-annotate', () => ({ useCanAnnotate: () => ref(true) }))

describe('page numbering', () => {
  it('uses stored numbers and truthful minimal unknowns', () => {
    expect(pagePosition(10, 3)).toBe('10/3')
    expect(pagePosition(null, 12)).toBe('–/12')
    expect(pagePosition(3, null)).toBe('3/–')
    expect(pagePosition()).toBe('–/–')
    expect(pageGalleryLabel('12345678-uuid', 10)).toBe('10')
    expect(pageGalleryLabel('12345678-uuid')).toBe('12345678')
    const card = mount(DocumentCard, {
      props: {
        library: 'x',
        documentUuid: 'd',
        pageUuid: 'p',
        names: [],
        pageNumber: 10,
        registeredPageCount: 3,
      },
    })
    // The compact form is hidden from assistive tech; the spoken form is sr-only text.
    expect(card.get('small > span[aria-hidden="true"]').text()).toBe('10/3')
    expect(card.get('.sr-only').text()).toBe('Page 10 of 3 registered pages')
    expect(card.find('small[aria-label]').exists()).toBe(false)
  })
  it('validates edits and sends explicit clears without changing page identity', async () => {
    const page = {
      version: 1,
      source_id: 'source',
      page_number: 10,
      registered_page_count: 3,
    } as PageResponse
    const wrapper = mount(PageNumberEditor, { props: { page } })
    const input = wrapper.get('input')
    await input.setValue('1.5')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await input.setValue('2')
    await wrapper.get('form').trigger('submit')
    expect(mocks.mutate).toHaveBeenLastCalledWith(
      {
        sourceId: 'source',
        payload: { version: 1, page_number: 2 },
      },
      { onSuccess: expect.any(Function) },
    )
    await input.setValue('')
    await wrapper.get('form').trigger('submit')
    expect(mocks.mutate).toHaveBeenLastCalledWith(
      {
        sourceId: 'source',
        payload: { version: 1, page_number: null },
      },
      { onSuccess: expect.any(Function) },
    )
    await wrapper.setProps({ page: { ...page, page_number: 3 } })
    expect((input.element as HTMLInputElement).value).toBe('3')
  })
})

it('preserves a page draft version on refresh and resets it when navigating to a different source', async () => {
  const page = { source_id: 'first', page_number: 1, version: 3 } as PageResponse
  const wrapper = mount(PageNumberEditor, { props: { page } })
  const input = wrapper.get('input')
  await input.trigger('focus')
  await input.setValue('2')
  await wrapper.setProps({ page: { ...page, version: 4, page_number: 7 } })
  expect((input.element as HTMLInputElement).value).toBe('2')
  await wrapper.get('form').trigger('submit')
  expect(mocks.mutate.mock.lastCall?.[0]).toEqual({
    sourceId: 'first',
    payload: { version: 3, page_number: 2 },
  })
  await wrapper.setProps({ page: { ...page, source_id: 'second', page_number: 9, version: 6 } })
  expect((input.element as HTMLInputElement).value).toBe('9')
  await input.trigger('focus')
  await input.setValue('10')
  await wrapper.get('form').trigger('submit')
  expect(mocks.mutate.mock.lastCall?.[0]).toEqual({
    sourceId: 'second',
    payload: { version: 6, page_number: 10 },
  })
  const success = mocks.mutate.mock.lastCall?.[1].onSuccess
  success({ source_id: 'second', page_number: 10, version: 7 })
  await wrapper.get('form').trigger('submit')
  expect(mocks.mutate.mock.lastCall?.[0]).toEqual({
    sourceId: 'second',
    payload: { version: 7, page_number: 10 },
  })
  wrapper.unmount()
})
