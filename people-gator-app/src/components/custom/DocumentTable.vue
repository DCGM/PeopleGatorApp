<script setup lang="ts">
import { computed, h, nextTick, ref, useId } from 'vue'
import { RouterLink } from 'vue-router'
import {
  columnVisibilityFeature,
  columnOrderingFeature,
  columnSizingFeature,
  columnResizingFeature,
  tableFeatures,
  useTable,
  FlexRender,
  type ColumnDef,
  type ColumnVisibilityState,
  type ColumnSizingState,
  type Header,
} from '@tanstack/vue-table'
import { ArrowUp, ArrowDown, ArrowUpDown, GripHorizontal, GripVertical, Plus, X } from '@lucide/vue'
import { type SortState } from '@/lib/sorting'
import type { DocumentResponse, DocumentSortField } from '@/client'
import DocumentFirstPage from './DocumentFirstPage.vue'
import DocumentSourceLink from './DocumentSourceLink.vue'
import { documentTitle, documentOpenLocation } from '@/viewmodels/document-list'
import {
  documentColumnSizing,
  annotationCount,
  annotationColumnId,
  DOCUMENT_ANNOTATION_GROUPS,
  DOCUMENT_ANNOTATION_STATES,
  defaultDocumentColumns,
  defaultDocumentColumnOrder,
  appendDocumentColumn,
  moveDocumentColumn,
  stepDocumentColumn,
  DOCUMENT_COLUMN_SORTS,
} from '@/viewmodels/document-table'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const annotationStateLabel = (id: string) =>
  DOCUMENT_ANNOTATION_STATES.find((state) => id === state.id || id.endsWith(`_${state.id}`))?.label

const tableId = useId()
const columnHeaderId = (id: string) => `${tableId}-${id}`

const props = defineProps<{ documents: DocumentResponse[]; loadingMore?: boolean }>()
const visibility = defineModel<ColumnVisibilityState>('visibility', { required: true })
const order = defineModel<string[]>('order', { required: true })
const sort = defineModel<SortState<DocumentSortField> | undefined>('sort')
function toggleSort(columnId: string) {
  const field = DOCUMENT_COLUMN_SORTS[columnId]
  if (!field) return
  sort.value =
    sort.value?.field !== field
      ? { field, direction: 'asc' }
      : sort.value.direction === 'asc'
        ? { field, direction: 'desc' }
        : undefined
}
function headerSort(columnId: string) {
  return sort.value && DOCUMENT_COLUMN_SORTS[columnId] === sort.value.field
    ? sort.value?.direction === 'asc'
      ? 'ascending'
      : 'descending'
    : undefined
}
function sortLabel(columnId: string, label: unknown) {
  const state = headerSort(columnId)
  return `Sort by ${label}: ${state === 'ascending' ? 'sort descending' : state === 'descending' ? 'clear sorting' : 'sort ascending'}`
}
const features = tableFeatures({
  columnVisibilityFeature,
  columnOrderingFeature,
  columnSizingFeature,
  columnResizingFeature,
})
const link = (document: DocumentResponse, text: string) =>
  h(
    RouterLink,
    {
      to: documentOpenLocation(document),
      'aria-label': `Open ${documentTitle(document)} in ${document.library}, document ${document.document_id}`,
      class: 'underline underline-offset-4',
    },
    () => text,
  )
const sizing = ref<ColumnSizingState>({})
const columns: ColumnDef<typeof features, DocumentResponse>[] = [
  {
    id: 'identity',
    ...documentColumnSizing('identity'),
    header: 'Document',
    enableHiding: false,
    cell: ({ row }) => link(row.original, `${row.original.library} · ${row.original.document_id}`),
  },
  {
    id: 'name',
    ...documentColumnSizing('name'),
    header: 'Document name',
    accessorFn: documentTitle,
    cell: ({ row }) => link(row.original, documentTitle(row.original)),
  },
  {
    id: 'ndk',
    ...documentColumnSizing('ndk'),
    header: 'NDK',
    cell: ({ row }) => h(DocumentSourceLink, { url: row.original.url }),
  },
  {
    id: 'first_page',
    ...documentColumnSizing('first_page'),
    header: 'First page',
    cell: ({ row }) => h(DocumentFirstPage, { document: row.original }),
  },
  {
    accessorKey: 'library',
    header: 'Library',
    ...documentColumnSizing('library'),
    cell: ({ row }) =>
      h(
        RouterLink,
        {
          to: { name: 'document-list', query: { library: row.original.library } },
          class: 'underline underline-offset-4',
        },
        () => row.original.library,
      ),
  },
  {
    accessorKey: 'document_id',
    ...documentColumnSizing('document_id'),
    header: 'Document ID',
    cell: ({ row }) => link(row.original, row.original.document_id),
  },
  {
    accessorKey: 'registered_page_count',
    ...documentColumnSizing('registered_page_count'),
    header: 'Pages',
    cell: ({ getValue }) => getValue() ?? 'Unknown',
  },
  {
    id: 'last_modified',
    ...documentColumnSizing('last_modified'),
    header: 'Last modified',
    accessorFn: (d) => d.last_touched_at,
    cell: ({ getValue }) =>
      getValue() ? new Date(String(getValue())).toLocaleString() : 'Unknown',
  },
  {
    id: 'modified_by',
    ...documentColumnSizing('modified_by'),
    header: 'Modified by',
    accessorFn: (d) => d.last_touched_by_user_name || d.last_touched_by_user_id || 'Unknown',
  },
  {
    id: 'api_key',
    ...documentColumnSizing('api_key'),
    header: 'API key',
    accessorFn: (d) => d.last_touched_by_api_key_name || d.last_touched_by_api_key_id || '—',
  },
  {
    accessorKey: 'linked_entity_count',
    ...documentColumnSizing('linked_entity_count'),
    header: 'Linked entities',
    cell: ({ getValue }) => getValue() ?? 'Unknown',
  },
  ...DOCUMENT_ANNOTATION_GROUPS.flatMap((group) =>
    DOCUMENT_ANNOTATION_STATES.map((state) => ({
      id: annotationColumnId(group.scope, state.id),
      ...documentColumnSizing(annotationColumnId(group.scope, state.id)),
      header:
        state.id === 'total'
          ? { all: 'Annotations', faces: 'Faces', mentions: 'Mentions' }[group.scope]
          : `${group.label}: ${state.label}`,
      accessorFn: (d: DocumentResponse) => annotationCount(d, state.id, group.scope),
      cell: ({ getValue }: { getValue: () => unknown }) => getValue() ?? 'Unknown',
    })),
  ),
]
// The document link fallback replaces the name, so it always takes the name's place.
const columnOrder = computed(() => {
  const ids = order.value.filter((id) => id !== 'identity')
  ids.splice(Math.max(0, ids.indexOf('name')), 0, 'identity')
  return ids
})
const ADD_COLUMN_MIN_WIDTH = 160
const orderId = (id: string) => (id === 'identity' ? 'name' : id)

const table = useTable({
  features,
  columns,
  columnResizeMode: 'onChange',
  data: computed(() => props.documents),
  getRowId: (row: DocumentResponse) => row.source_id,
  state: computed(() => ({
    columnOrder: columnOrder.value,
    columnSizing: sizing.value,
    columnVisibility: {
      ...visibility.value,
      identity: visibility.value.name === false && visibility.value.document_id !== true,
    },
  })),
  onColumnSizingChange: (next) => {
    const requested = typeof next === 'function' ? next(sizing.value) : next
    sizing.value = Object.fromEntries(
      Object.entries(requested).map(([id, value]) => {
        const { minSize, maxSize } = documentColumnSizing(id)
        return [id, Math.min(maxSize, Math.max(minSize, value))]
      }),
    )
  },
  onColumnVisibilityChange: (next) => {
    visibility.value = typeof next === 'function' ? next(visibility.value) : next
  },
})
// Header-only keyboard sizing follows the same bounds/state as mouse and touch.
function resizeKey(event: KeyboardEvent, header: Header<typeof features, DocumentResponse>) {
  const { minSize, maxSize, size } = documentColumnSizing(header.column.id)
  const step = event.shiftKey ? 40 : 10
  const width = (
    {
      ArrowLeft: header.column.getSize() - step,
      ArrowRight: header.column.getSize() + step,
      Home: minSize,
      End: maxSize,
      Enter: size,
    } as Record<string, number>
  )[event.key]
  if (width === undefined) return
  event.preventDefault()
  event.stopPropagation()
  table.setColumnSizing((current) => ({ ...current, [header.column.id]: width }))
}

const columnLabel = (id: string) =>
  String(columns.find((c) => (c.id ?? ('accessorKey' in c ? c.accessorKey : '')) === id)?.header)
const visibleIds = () => table.getVisibleLeafColumns().map((c) => orderId(c.id))
const annotationGroupOf = (id: string) =>
  DOCUMENT_ANNOTATION_GROUPS.find((g) =>
    DOCUMENT_ANNOTATION_STATES.some((s) => annotationColumnId(g.scope, s.id) === id),
  )
// Only hidden fields can be added; each group keeps the default field order.
const addGroups = computed(() => {
  const hidden = defaultDocumentColumnOrder().filter((id) => visibility.value[id] === false)
  return [
    {
      id: 'document',
      label: 'Document fields',
      items: hidden
        .filter((id) => !annotationGroupOf(id))
        .map((id) => ({ id, label: columnLabel(id), name: columnLabel(id) })),
    },
    ...DOCUMENT_ANNOTATION_GROUPS.map((group) => ({
      id: group.id,
      label: group.label,
      items: hidden
        .filter((id) => annotationGroupOf(id) === group)
        .map((id) => ({
          id,
          label: annotationStateLabel(id) ?? id,
          name: `${group.label}: ${annotationStateLabel(id)}`,
        })),
    })),
  ].filter((group) => group.items.length)
})
const addOpen = ref(false)
const addTrigger = ref<InstanceType<typeof Button> | null>(null)
function openAddMenu() {
  ;(addTrigger.value?.$el as HTMLElement | undefined)?.focus()
  addOpen.value = true
}
function addColumn(id: string) {
  order.value = appendDocumentColumn(order.value, visibleIds(), id)
  visibility.value = { ...visibility.value, [id]: true }
}
function restoreDefaults() {
  visibility.value = defaultDocumentColumns()
  order.value = defaultDocumentColumnOrder()
}

// Removal needs a second, confirming activation of the same button.
const armed = ref<string | null>(null)
function removeColumn(id: string) {
  if (armed.value !== id) {
    armed.value = id
    return
  }
  armed.value = null
  visibility.value = { ...visibility.value, [id]: false }
}

const moveStatus = ref('')
const tableElement = ref<HTMLTableElement | null>(null)
async function focusMoveHandle(id: string) {
  await nextTick()
  tableElement.value?.querySelector<HTMLElement>(`[data-move-column="${id}"]`)?.focus()
}
function announceMove(id: string) {
  const visible = visibleIds()
  moveStatus.value = `${columnLabel(id)} moved to position ${visible.indexOf(orderId(id)) + 1} of ${visible.length}`
}
function moveKey(event: KeyboardEvent, id: string) {
  const step = ({ ArrowLeft: -1, ArrowRight: 1 } as const)[event.key as 'ArrowLeft' | 'ArrowRight']
  if (!step) return
  event.preventDefault()
  order.value = stepDocumentColumn(order.value, visibleIds(), orderId(id), step)
  void focusMoveHandle(id).then(() => announceMove(id))
}

type Drop = { target: string; after: boolean }
const dragging = ref<{ id: string; drop?: Drop } | null>(null)
function dropAt(x: number, id: string): Drop | undefined {
  const cells = [
    ...(tableElement.value?.querySelectorAll<HTMLElement>('thead th[data-column]') ?? []),
  ]
  const cell = cells.find((c) => x < c.getBoundingClientRect().right) ?? cells[cells.length - 1]
  const target = cell?.dataset.column
  if (!cell || !target || target === id) return undefined
  const bounds = cell.getBoundingClientRect()
  return { target, after: x > bounds.left + bounds.width / 2 }
}
function startMove(event: PointerEvent, id: string) {
  if (event.button !== 0) return
  event.preventDefault()
  const handle = event.currentTarget as HTMLElement
  const viewport = handle.closest<HTMLElement>('[data-slot="scroll-area-viewport"]')
  handle.setPointerCapture?.(event.pointerId)
  dragging.value = { id }
  const move = (e: PointerEvent) => {
    // Scroll near the region edges so off-screen columns can be reached.
    const bounds = viewport?.getBoundingClientRect()
    if (viewport && bounds) {
      if (e.clientX < bounds.left + 48) viewport.scrollLeft -= 24
      else if (e.clientX > bounds.right - 48) viewport.scrollLeft += 24
    }
    dragging.value = { id, drop: dropAt(e.clientX, id) }
  }
  const end = (e: PointerEvent) => {
    handle.removeEventListener('pointermove', move)
    handle.removeEventListener('pointerup', end)
    handle.removeEventListener('pointercancel', end)
    const drop = dragging.value?.drop
    dragging.value = null
    if (e.type !== 'pointerup' || !drop) return
    order.value = moveDocumentColumn(order.value, orderId(id), orderId(drop.target), drop.after)
    announceMove(id)
  }
  handle.addEventListener('pointermove', move)
  handle.addEventListener('pointerup', end)
  handle.addEventListener('pointercancel', end)
}
</script>

<template>
  <!-- On mobile, fill the viewport below the sticky h-13 top bar so it never covers the header. -->
  <div class="flex h-[calc(100dvh-3.25rem)] min-w-0 flex-col lg:h-auto lg:min-h-0">
    <p :id="`${tableId}-counts`" class="sr-only">
      Counts cover the entire registered document. All annotations combines faces and text mentions;
      each group includes total, automatic, manual, verified and unassigned counts. Pages counts
      registered pages only. Unknown means no recorded value.
    </p>
    <p class="sr-only" role="status">{{ moveStatus }}</p>
    <ScrollArea
      class="relative min-h-0 flex-1 w-full min-w-0 max-w-full overflow-hidden rounded-md border"
      orientation="both"
      type="always"
      :viewport-props="{
        tabindex: 0,
        role: 'region',
        'aria-label': 'Documents table, scroll for more rows and columns',
      }"
    >
      <table
        ref="tableElement"
        :aria-describedby="`${tableId}-counts`"
        class="min-w-full table-fixed caption-bottom text-sm"
        :style="{ width: `${table.getTotalSize() + ADD_COLUMN_MIN_WIDTH}px` }"
      >
        <colgroup>
          <col
            v-for="column in table.getVisibleLeafColumns()"
            :key="column.id"
            :data-column="column.id"
            :style="{ width: `${column.getSize()}px` }"
          />
          <!-- Without a width, the add column takes the remaining table width. -->
          <col data-add-column />
        </colgroup>
        <TableHeader class="sticky top-0 z-10 bg-background">
          <TableRow v-for="group in table.getHeaderGroups()" :key="group.id">
            <TableHead
              v-for="header in group.headers.filter((h) => group.depth === 0 || h.column.parent)"
              :key="header.id"
              :id="columnHeaderId(header.column.id)"
              :data-column="header.column.columns.length ? undefined : header.column.id"
              :colspan="header.colSpan"
              :rowspan="header.isPlaceholder ? table.getHeaderGroups().length : undefined"
              :scope="header.column.columns.length ? 'colgroup' : 'col'"
              :aria-sort="headerSort(header.column.id)"
              :style="{ width: `${header.getSize()}px` }"
              class="relative border-r pr-4 align-top last:border-r-0"
              :class="{
                'opacity-50': dragging?.id === header.column.id,
                'before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-primary':
                  dragging?.drop?.target === header.column.id && !dragging.drop.after,
                'after:absolute after:inset-y-0 after:right-0 after:w-0.5 after:bg-primary':
                  dragging?.drop?.target === header.column.id && dragging.drop.after,
              }"
            >
              <div
                v-if="!header.column.columns.length"
                class="flex items-center justify-between gap-1 pt-1"
              >
                <Button
                  variant="ghost"
                  size="icon-xs"
                  class="cursor-grab touch-none active:cursor-grabbing"
                  :data-move-column="header.column.id"
                  :aria-label="`Move ${columnLabel(header.column.id)} column`"
                  aria-keyshortcuts="ArrowLeft ArrowRight"
                  title="Drag to move; arrow keys move"
                  @pointerdown="startMove($event, header.column.id)"
                  @keydown="moveKey($event, header.column.id)"
                >
                  <GripHorizontal aria-hidden="true" />
                </Button>
                <Button
                  v-if="header.column.getCanHide()"
                  :data-remove-column="header.column.id"
                  :variant="armed === header.column.id ? 'destructive' : 'ghost'"
                  :size="armed === header.column.id ? 'xs' : 'icon-xs'"
                  :aria-label="
                    armed === header.column.id
                      ? `Confirm removing ${columnLabel(header.column.id)} column`
                      : `Remove ${columnLabel(header.column.id)} column`
                  "
                  :title="armed === header.column.id ? undefined : 'Remove column'"
                  @click="removeColumn(header.column.id)"
                  @blur="armed === header.column.id && (armed = null)"
                  @keydown.escape="armed = null"
                >
                  <X aria-hidden="true" /><span v-if="armed === header.column.id">Remove</span>
                </Button>
              </div>
              <div class="flex items-center gap-1 pb-2 whitespace-normal">
                <Button
                  v-if="DOCUMENT_COLUMN_SORTS[header.column.id]"
                  variant="ghost"
                  size="icon"
                  class="size-8 shrink-0"
                  :aria-label="sortLabel(header.column.id, header.column.columnDef.header)"
                  @click="toggleSort(header.column.id)"
                >
                  <ArrowUp
                    v-if="headerSort(header.column.id) === 'ascending'"
                    class="size-4"
                    aria-hidden="true"
                  />
                  <ArrowDown
                    v-else-if="headerSort(header.column.id) === 'descending'"
                    class="size-4"
                    aria-hidden="true"
                  />
                  <ArrowUpDown v-else class="size-4" aria-hidden="true" />
                </Button>
                <span class="min-w-0 [overflow-wrap:anywhere]"
                  ><FlexRender
                    :render="header.column.columnDef.header"
                    :props="header.getContext()"
                /></span>
              </div>
              <Button
                v-if="!header.column.columns.length"
                variant="ghost"
                size="icon"
                class="absolute inset-y-0 right-0 h-full w-3 cursor-col-resize touch-none select-none"
                role="separator"
                aria-orientation="vertical"
                :aria-label="`Resize ${header.column.parent ? header.column.parent.columnDef.header + ': ' : ''}${header.column.columnDef.header} column`"
                :aria-valuenow="header.column.getSize()"
                :aria-valuemin="header.column.columnDef.minSize"
                :aria-valuemax="header.column.columnDef.maxSize"
                :aria-controls="columnHeaderId(header.column.id)"
                title="Drag to resize; arrow keys adjust; Enter restores default"
                @mousedown.stop.prevent="header.getResizeHandler()($event)"
                @touchstart.stop="header.getResizeHandler()($event)"
                @click.stop.prevent
                @dblclick.stop.prevent="header.column.resetSize()"
                @keydown="resizeKey($event, header)"
              >
                <GripVertical class="size-3" aria-hidden="true" />
              </Button>
            </TableHead>
            <TableHead
              :id="columnHeaderId('add')"
              data-add-column
              scope="col"
              class="relative p-0"
              :rowspan="table.getHeaderGroups().length"
            >
              <DropdownMenu v-model:open="addOpen">
                <DropdownMenuTrigger as-child>
                  <Button
                    ref="addTrigger"
                    variant="ghost"
                    class="absolute inset-0 h-full w-full justify-start rounded-none"
                  >
                    <Plus aria-hidden="true" /><span>Add column</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  <template v-for="(group, index) in addGroups" :key="group.id">
                    <DropdownMenuSeparator v-if="index" />
                    <DropdownMenuGroup>
                      <DropdownMenuLabel>{{ group.label }}</DropdownMenuLabel>
                      <DropdownMenuItem
                        v-for="item in group.items"
                        :key="item.id"
                        :aria-label="item.name"
                        @select="addColumn(item.id)"
                        >{{ item.label }}</DropdownMenuItem
                      >
                    </DropdownMenuGroup>
                  </template>
                  <DropdownMenuItem v-if="!addGroups.length" disabled
                    >All columns shown</DropdownMenuItem
                  >
                  <DropdownMenuSeparator />
                  <DropdownMenuItem @select="restoreDefaults"
                    >Restore default columns</DropdownMenuItem
                  >
                </DropdownMenuContent>
              </DropdownMenu>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="row in table.getRowModel().rows" :key="row.id">
            <TableCell
              v-for="cell in row.getVisibleCells()"
              :key="cell.id"
              :data-column="cell.column.id"
              class="border-r whitespace-normal [overflow-wrap:anywhere]"
              :style="{ width: `${cell.column.getSize()}px` }"
              :headers="
                cell.column.parent
                  ? `${columnHeaderId(cell.column.parent.id)} ${columnHeaderId(cell.column.id)}`
                  : columnHeaderId(cell.column.id)
              "
            >
              <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
            </TableCell>
            <!-- Pointer shortcut only: the header holds the accessible control. -->
            <TableCell
              data-add-column
              :headers="columnHeaderId('add')"
              class="cursor-pointer"
              @click="openAddMenu"
            />
          </TableRow>
          <TableRow v-if="loadingMore" data-slot="document-loading-row" aria-hidden="true">
            <TableCell
              v-for="column in table.getVisibleLeafColumns()"
              :key="column.id"
              :data-column="column.id"
              class="border-r"
              :style="{ width: `${column.getSize()}px` }"
            >
              <Skeleton :class="column.id === 'first_page' ? 'h-28 w-20' : 'h-4 w-2/3'" />
            </TableCell>
            <TableCell data-add-column />
          </TableRow>
        </TableBody>
      </table>
      <slot name="list-end" />
    </ScrollArea>
  </div>
</template>
