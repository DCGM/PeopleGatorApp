import { describe, expect, it, vi, afterEach } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import {
  appendDocumentColumn,
  documentCreator,
  defaultDocumentColumnOrder,
  defaultDocumentColumns,
  DOCUMENT_COLUMN_ORDER_STORAGE_KEY,
  DOCUMENT_COLUMNS_STORAGE_KEY,
  DOCUMENT_COLUMN_SIZING_STORAGE_KEY,
  moveDocumentColumn,
  readDocumentColumnOrder,
  readDocumentColumns,
  readDocumentColumnSizing,
  normalizeDocumentColumnSizing,
  stepDocumentColumn,
  useDocumentColumnOrder,
  useDocumentColumns,
  useDocumentColumnSizing,
} from '@/viewmodels/document-table'

afterEach(() => {
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
  window.localStorage.clear()
})
describe('document column durable preferences', () => {
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
    expect(JSON.parse(window.localStorage.getItem(DOCUMENT_COLUMNS_STORAGE_KEY)!)).toEqual(
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
  it('keeps controls usable when accessing or writing localStorage throws', async () => {
    vi.stubGlobal('localStorage', {
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
  it('saves the order across tab sessions', async () => {
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
    expect(JSON.parse(window.localStorage.getItem(DOCUMENT_COLUMN_ORDER_STORAGE_KEY)!)[0]).toBe(
      'library',
    )
    wrapper.unmount()
    window.sessionStorage.clear()
    wrapper = mount(Component)
    expect(order.value[0]).toBe('library')
    wrapper.unmount()
  })
})

describe('creation column preferences', () => {
  it('keeps creation hidden on existing tabs and persists add, move and remove choices', () => {
    expect(readDocumentColumns({ getItem: () => '{"name":true}' })).toMatchObject({ created: false, created_by: false })
    const saved = { ...defaultDocumentColumns(), created: true, created_by: true }
    expect(readDocumentColumns({ getItem: () => JSON.stringify(saved) })).toEqual(saved)
    const moved = moveDocumentColumn(defaultDocumentColumnOrder(), 'created_by', 'name', true)
    expect(readDocumentColumnOrder({ getItem: () => JSON.stringify(moved) })).toEqual(moved)
    expect(readDocumentColumns({ getItem: () => JSON.stringify({ ...saved, created: false }) }).created).toBe(false)
  })
  it('uses stable IDs when creator labels are unavailable', () => {
    const document = { source_id: 'source', source_type: 'document' as const, url: 'https://example.test', library: 'test', document_id: 'archive' }
    expect(documentCreator(document)).toBe('Unknown')
    expect(documentCreator({ ...document, created_by_user_id: 'user-id' })).toBe('user-id')
    expect(documentCreator({ ...document, created_by_user_id: 'user-id', created_by_api_key_id: 'key-id' })).toBe('user-id (key-id)')
  })
})

describe('layout storage boundaries', () => {
  function mountLayout() {
    let layout!: {
      columns: ReturnType<typeof useDocumentColumns>
      order: ReturnType<typeof useDocumentColumnOrder>
      sizing: ReturnType<typeof useDocumentColumnSizing>
    }
    const wrapper = mount(
      defineComponent({
        setup() {
          layout = {
            columns: useDocumentColumns(),
            order: useDocumentColumnOrder(),
            sizing: useDocumentColumnSizing(),
          }
          return () => null
        },
      }),
    )
    return { wrapper, layout }
  }

  it('imports legacy tab choices once, then restores the complete layout without a session', async () => {
    window.sessionStorage.setItem(
      DOCUMENT_COLUMNS_STORAGE_KEY,
      '{"library":false,"document_id":true}',
    )
    window.sessionStorage.setItem(DOCUMENT_COLUMN_ORDER_STORAGE_KEY, '["name","first_page"]')
    let mounted = mountLayout()
    expect(mounted.layout.columns.value.library).toBe(false)
    expect(mounted.layout.columns.value.document_id).toBe(true)
    expect(mounted.layout.order.value.slice(0, 2)).toEqual(['name', 'first_page'])
    mounted.layout.sizing.value = { name: 510, identity: 410 }
    await nextTick()
    mounted.wrapper.unmount()
    window.sessionStorage.clear()
    mounted = mountLayout()
    expect(mounted.layout.columns.value.library).toBe(false)
    expect(mounted.layout.order.value[0]).toBe('name')
    expect(mounted.layout.sizing.value).toEqual({ name: 510, identity: 410 })
    mounted.wrapper.unmount()
  })

  it('never replaces durable choices with stale legacy tab settings, including after a reset', () => {
    window.localStorage.setItem(
      DOCUMENT_COLUMNS_STORAGE_KEY,
      JSON.stringify(defaultDocumentColumns()),
    )
    window.localStorage.setItem(
      DOCUMENT_COLUMN_ORDER_STORAGE_KEY,
      JSON.stringify(defaultDocumentColumnOrder()),
    )
    window.localStorage.setItem(DOCUMENT_COLUMN_SIZING_STORAGE_KEY, '{}')
    window.sessionStorage.setItem(DOCUMENT_COLUMNS_STORAGE_KEY, '{"name":false}')
    window.sessionStorage.setItem(DOCUMENT_COLUMN_ORDER_STORAGE_KEY, '["library"]')
    const { wrapper, layout } = mountLayout()
    expect(layout.columns.value).toEqual(defaultDocumentColumns())
    expect(layout.order.value).toEqual(defaultDocumentColumnOrder())
    expect(layout.sizing.value).toEqual({})
    wrapper.unmount()
  })

  it('recovers malformed durable settings without resurrecting an old tab layout', () => {
    for (const key of [
      DOCUMENT_COLUMNS_STORAGE_KEY,
      DOCUMENT_COLUMN_ORDER_STORAGE_KEY,
      DOCUMENT_COLUMN_SIZING_STORAGE_KEY,
    ]) {
      window.localStorage.setItem(key, '{')
    }
    window.sessionStorage.setItem(DOCUMENT_COLUMNS_STORAGE_KEY, '{"name":false}')
    const { wrapper, layout } = mountLayout()
    expect(layout.columns.value).toEqual(defaultDocumentColumns())
    expect(layout.order.value).toEqual(defaultDocumentColumnOrder())
    expect(layout.sizing.value).toEqual({})
    wrapper.unmount()
  })

  it('validates known widths, drops obsolete/invalid values and clamps supported fields', () => {
    expect(
      normalizeDocumentColumnSizing({
        name: 5000,
        identity: 1,
        faces_total: 190,
        library: -1,
        ndk: '120',
        document_id: Number.NaN,
        first_page: Number.POSITIVE_INFINITY,
        total: 0,
        obsolete: 300,
      }),
    ).toEqual({ name: 720, identity: 200, faces_total: 190 })
    for (const raw of [null, '{', '[]', '42', '{"obsolete":200}']) {
      expect(readDocumentColumnSizing({ getItem: () => raw })).toEqual({})
    }
    expect(readDocumentColumnSizing({ getItem: () => '{"name":400,"ndk":1}' })).toEqual({
      name: 400,
      ndk: 80,
    })
    expect(
      readDocumentColumnSizing({
        getItem: () => {
          throw new Error('denied')
        },
      }),
    ).toEqual({})
  })

  it('retains readable settings and in-memory changes when localStorage writes hit quota', async () => {
    window.localStorage.setItem(DOCUMENT_COLUMN_SIZING_STORAGE_KEY, '{"name":430}')
    const getItem = window.localStorage.getItem.bind(window.localStorage)
    vi.stubGlobal('localStorage', {
      getItem,
      setItem: () => {
        throw new Error('quota')
      },
    })
    const { wrapper, layout } = mountLayout()
    expect(layout.sizing.value).toEqual({ name: 430 })
    layout.columns.value.name = false
    layout.order.value = ['library', ...layout.order.value.filter((id) => id !== 'library')]
    layout.sizing.value = { name: 600 }
    await nextTick()
    expect(layout.columns.value.name).toBe(false)
    expect(layout.order.value[0]).toBe('library')
    expect(layout.sizing.value.name).toBe(600)
    wrapper.unmount()
  })
})
