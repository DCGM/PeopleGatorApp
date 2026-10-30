import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  COUNT_KEYS,
  COUNT_OPTIONS,
  parseMinimum,
  readCountFilters,
  useAnnotationCounts,
} from '@/viewmodels/annotation-counts'
import { defaultDirection, readSort } from '@/lib/sorting'
import { DOCUMENT_SORTS, PAGE_SORTS, DOCUMENT_BROWSE_DEFAULT } from '@/viewmodels/sort-options'
import {
  DOCUMENT_COLUMN_SORTS,
  DOCUMENT_ANNOTATION_GROUPS,
  DOCUMENT_ANNOTATION_STATES,
  annotationColumnId,
} from '@/viewmodels/document-table'
import DocumentListSearchBar from '@/components/custom/DocumentListSearchBar.vue'
import AnnotationCountControl from '@/components/custom/AnnotationCountControl.vue'

vi.mock('@/query/people-filter-options', () => ({
  useActorLabels: () => ({ labels: ref({}) }),
  useSourceLabels: () => ({ labels: ref({}) }),
  useSourceOptions: () => ({ options: ref([]), isLoading: ref(false), hasNextPage: ref(false) }),
  useActorOptions: () => ({ options: ref([]), isLoading: ref(false), hasNextPage: ref(false) }),
}))
vi.mock('@/components/custom/SharedFilterControls.vue', () => ({
  default: { template: '<div />' },
}))
const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach((fn) => fn()))

describe('annotation count controls and URL state', () => {
  it('offers the same complete hierarchy for both resources and column headers', () => {
    expect(COUNT_OPTIONS).toHaveLength(15)
    for (const option of COUNT_OPTIONS) {
      expect(DOCUMENT_SORTS).toContainEqual(option)
      expect(PAGE_SORTS).toContainEqual(option)
      expect(defaultDirection(option.value)).toBe('desc')
    }
    for (const group of DOCUMENT_ANNOTATION_GROUPS)
      for (const state of DOCUMENT_ANNOTATION_STATES)
        expect(DOCUMENT_COLUMN_SORTS[annotationColumnId(group.scope, state.id)]).toBe(
          `${group.scope === 'all' ? 'annotations' : group.scope}_${state.id}_count`,
        )
    expect(
      readSort({}, { field: 'sort', direction: 'dir' }, DOCUMENT_SORTS, DOCUMENT_BROWSE_DEFAULT),
    ).toEqual(DOCUMENT_BROWSE_DEFAULT)
  })

  it('parses only non-negative decimal integers and retains invalid copied values', () => {
    for (const input of ['0', '2', '007']) expect(parseMinimum(input)).toBe(Number(input))
    for (const input of [
      '',
      '-1',
      '1.5',
      '1.0',
      '1e2',
      ' 2 ',
      '9007199254740992',
      null,
      ['1'],
      'NaN',
    ])
      expect(parseMinimum(input)).toBeUndefined()
    for (const option of COUNT_OPTIONS) {
      const value = readCountFilters({ [`min_${option.value}`]: '0' })
      expect(value.params).toEqual({ [`filter.min_${option.value}`]: 0 })
      expect(value.error).toBeUndefined()
      expect(value.tags[0]?.label).toContain('≥ 0')
    }
    const invalid = readCountFilters({
      min_faces_total_count: '-1',
      min_mentions_manual_count: '2',
    })
    expect(invalid.error).toBeTruthy()
    expect(invalid.tags).toHaveLength(2)
    expect(invalid.params).toEqual({ 'filter.min_mentions_manual_count': 2 })
  })

  it('keeps independent tags, resets cursors, restores history and clears filters while preserving search and sort', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/documents', component: { template: '<div />' } }],
    })
    await router.push(
      '/documents?q=ledger&sort=faces_total_count&library=preview-counts&min_faces_manual_count=2&min_mentions_total_count=3&cursor=old&page_cursor=old',
    )
    let counts!: ReturnType<typeof useAnnotationCounts>
    const shell = defineComponent({
      setup() {
        counts = useAnnotationCounts()
        return () =>
          h(DocumentListSearchBar, { searchTerm: 'ledger', unassigned: 'all', resultCount: 1 })
      },
    })
    const wrapper = mount(shell, { global: { plugins: [router] }, attachTo: document.body })
    cleanups.push(() => wrapper.unmount())
    await flushPromises()
    expect(counts.params.value).toEqual({
      'filter.min_faces_manual_count': 2,
      'filter.min_mentions_total_count': 3,
    })
    expect(wrapper.text()).toContain('Faces: Manual ≥ 2')
    expect(wrapper.text()).toContain('Text mentions: Total ≥ 3')
    // Individual count removal preserves other filters and immediately changes query state.
    counts.remove(counts.tags.value[0]!)
    await flushPromises()
    expect(router.currentRoute.value.query.min_faces_manual_count).toBeUndefined()
    expect(router.currentRoute.value.query.cursor).toBeUndefined()
    expect(router.currentRoute.value.query.page_cursor).toBeUndefined()
    expect(counts.params.value).toEqual({ 'filter.min_mentions_total_count': 3 })
    router.back()
    await flushPromises()
    expect(counts.params.value['filter.min_faces_manual_count']).toBe(2)
    router.forward()
    await flushPromises()
    expect(counts.params.value['filter.min_faces_manual_count']).toBeUndefined()
    const clear = wrapper.findAll('button').find((button) => button.text().includes('Clear all'))!
    await clear.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.q).toBe('ledger')
    expect(router.currentRoute.value.query.sort).toBe('faces_total_count')
    expect(counts.tags.value).toHaveLength(0)
    expect(COUNT_KEYS.some((key) => key in router.currentRoute.value.query)).toBe(false)
    counts.set('annotations_verified_count', 0)
    await flushPromises()
    expect(counts.params.value['filter.min_annotations_verified_count']).toBe(0)
  })

  it('applies hierarchical choices and rejects fractional text without changing the URL', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/documents', component: { template: '<div />' } }],
    })
    await router.push('/documents')
    const wrapper = mount(AnnotationCountControl, {
      global: { plugins: [router] },
      attachTo: document.body,
    })
    cleanups.push(() => wrapper.unmount())
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const selects = wrapper.findAllComponents({ name: 'FilterSingleSelect' })
    // Popover content is teleported; Vue's component tree keeps the setting controls reachable.
    expect(selects).toHaveLength(2)
    selects[0]!.vm.$emit('update:modelValue', 'faces')
    selects[1]!.vm.$emit('update:modelValue', 'unassigned')
    const input = document.querySelector('input[aria-label="Minimum count"]') as HTMLInputElement
    await router.push('/documents?min_faces_unassigned_count=3')
    await flushPromises()
    expect(input.value).toBe('3')
    input.value = '1.5'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    document
      .querySelector('form[aria-label="Minimum annotation count"]')!
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('whole number')
    expect(router.currentRoute.value.query).toEqual({ min_faces_unassigned_count: '3' })
    input.value = '2'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    document
      .querySelector('form[aria-label="Minimum annotation count"]')!
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(router.currentRoute.value.query.min_faces_unassigned_count).toBe('2')
  })
})
