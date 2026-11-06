import { describe, expect, it, vi, afterEach } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import {
  appendDocumentColumn,
  defaultDocumentColumnOrder,
  defaultDocumentColumns,
  DOCUMENT_COLUMN_ORDER_STORAGE_KEY,
  DOCUMENT_COLUMNS_STORAGE_KEY,
  moveDocumentColumn,
  readDocumentColumnOrder,
  readDocumentColumns,
  stepDocumentColumn,
  useDocumentColumnOrder,
  useDocumentColumns,
} from '@/viewmodels/document-table'

afterEach(() => {
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
})
describe('document column session preferences', () => {
  it.each([null, '', 'null', '[]', '42', '{', '{"obsolete":true}', '{"name":"false"}'])(
    'falls back for invalid or obsolete saved selections (%s)',
    (raw) => {
      expect(readDocumentColumns({ getItem: () => raw })).toEqual(defaultDocumentColumns())
    },
  )
  it('retains valid choices and ignores obsolete IDs and invalid values', () => {
    const getItem = () =>
      '{"name":false,"ndk":true,"faces_total":false,"obsolete":true,"library":"bad"}'
    expect(readDocumentColumns({ getItem })).toEqual({
      ...defaultDocumentColumns(),
      name: false,
      ndk: true,
      faces_total: false,
    })
    expect(
      readDocumentColumns({
        getItem: () => {
          throw new Error('denied')
        },
      }),
    ).toEqual(defaultDocumentColumns())
  })
  it('saves changes and restores them on remount, including restore defaults', async () => {
    let columns!: ReturnType<typeof useDocumentColumns>
    const Component = defineComponent({
      setup() {
        columns = useDocumentColumns()
        return () => null
      },
    })
    let wrapper = mount(Component)
    columns.value = { ...columns.value, name: false, ndk: true }
    await nextTick()
    expect(JSON.parse(window.sessionStorage.getItem(DOCUMENT_COLUMNS_STORAGE_KEY)!)).toEqual(
      columns.value,
    )
    wrapper.unmount()
    wrapper = mount(Component)
    expect(columns.value).toEqual({ ...defaultDocumentColumns(), name: false, ndk: true })
    columns.value = defaultDocumentColumns()
    await nextTick()
    wrapper.unmount()
    wrapper = mount(Component)
    expect(columns.value).toEqual(defaultDocumentColumns())
    wrapper.unmount()
  })
  it('keeps controls usable when accessing or writing sessionStorage throws', async () => {
    vi.stubGlobal('sessionStorage', {
      getItem: () => {
        throw new Error('denied')
      },
      setItem: () => {
        throw new Error('denied')
      },
    })
    let columns!: ReturnType<typeof useDocumentColumns>
    const wrapper = mount(
      defineComponent({
        setup() {
          columns = useDocumentColumns()
          return () => null
        },
      }),
    )
    columns.value.ndk = true
    await nextTick()
    expect(columns.value.ndk).toBe(true)
    wrapper.unmount()
  })
})
describe('document column order', () => {
  it.each([null, '', '{', '{"name":0}', '42'])(
    'falls back for an invalid saved order (%s)',
    (raw) => {
      expect(readDocumentColumnOrder({ getItem: () => raw })).toEqual(defaultDocumentColumnOrder())
    },
  )
  it('keeps a saved order, drops unknown/duplicate IDs and appends new fields', () => {
    const order = readDocumentColumnOrder({
      getItem: () => '["library","obsolete","name","library",7]',
    })
    expect(order.slice(0, 2)).toEqual(['library', 'name'])
    expect([...order].sort()).toEqual([...defaultDocumentColumnOrder()].sort())
  })
  it('moves, steps and appends columns without disturbing the others', () => {
    const order = ['a', 'b', 'c', 'd', 'e']
    expect(moveDocumentColumn(order, 'e', 'b', false)).toEqual(['a', 'e', 'b', 'c', 'd'])
    expect(moveDocumentColumn(order, 'a', 'c', true)).toEqual(['b', 'c', 'a', 'd', 'e'])
    expect(moveDocumentColumn(order, 'a', 'missing', true)).toBe(order)
    // Steps skip hidden IDs (b, d) and stop at either visible end.
    expect(stepDocumentColumn(order, ['a', 'c', 'e'], 'a', 1)).toEqual(['b', 'c', 'a', 'd', 'e'])
    expect(stepDocumentColumn(order, ['a', 'c', 'e'], 'a', -1)).toBe(order)
    expect(appendDocumentColumn(order, ['a', 'c'], 'e')).toEqual(['a', 'b', 'c', 'e', 'd'])
    expect(appendDocumentColumn(order, [], 'c')).toEqual(['c', 'a', 'b', 'd', 'e'])
  })
  it('saves the order for the tab session', async () => {
    let order!: ReturnType<typeof useDocumentColumnOrder>
    const Component = defineComponent({
      setup() {
        order = useDocumentColumnOrder()
        return () => null
      },
    })
    let wrapper = mount(Component)
    order.value = moveDocumentColumn(order.value, 'library', 'first_page', false)
    await nextTick()
    expect(JSON.parse(window.sessionStorage.getItem(DOCUMENT_COLUMN_ORDER_STORAGE_KEY)!)[0]).toBe(
      'library',
    )
    wrapper.unmount()
    wrapper = mount(Component)
    expect(order.value[0]).toBe('library')
    wrapper.unmount()
  })
})
