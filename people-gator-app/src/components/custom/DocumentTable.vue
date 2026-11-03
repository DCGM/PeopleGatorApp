<script setup lang="ts">
import { computed, h, ref, useId } from 'vue'
import { RouterLink } from 'vue-router'
import {
  columnVisibilityFeature,
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
import { ArrowUp, ArrowDown, ArrowUpDown, Settings2, GripVertical } from '@lucide/vue'
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
  DOCUMENT_COLUMN_SORTS,
} from '@/viewmodels/document-table'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const annotationStateLabel = (id: string) =>
  DOCUMENT_ANNOTATION_STATES.find((state) => id === state.id || id.endsWith(`_${state.id}`))?.label

const tableId = useId()
const columnHeaderId = (id: string) => `${tableId}-${id}`

const props = defineProps<{ documents: DocumentResponse[]; loadingMore?: boolean }>()
const visibility = defineModel<ColumnVisibilityState>('visibility', { required: true })
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
// Keep the eight default fields first, retaining stable IDs for saved selections.
const leading = [
  'first_page',
  'name',
  'library',
  'registered_page_count',
  'linked_entity_count',
  'total',
  'faces_total',
  'mentions_total',
]
columns.sort((a, b) => {
  const rank = (c: typeof a) => {
    const i = leading.indexOf(c.id ?? ('accessorKey' in c ? String(c.accessorKey) : ''))
    return i < 0 ? leading.length : i
  }
  return rank(a) - rank(b)
})

const table = useTable({
  features,
  columns,
  columnResizeMode: 'onChange',
  data: computed(() => props.documents),
  getRowId: (row: DocumentResponse) => row.source_id,
  state: computed(() => ({
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
</script>

<template>
  <div class="flex h-dvh min-w-0 flex-col gap-3 lg:h-auto lg:min-h-0">
    <div class="flex flex-wrap items-center gap-2 lg:shrink-0">
      <Popover>
        <PopoverTrigger as-child
          ><Button variant="outline"
            ><Settings2 aria-hidden="true" />Columns</Button
          ></PopoverTrigger
        >
        <PopoverContent
          align="start"
          class="max-h-[min(70dvh,var(--reka-popover-content-available-height))] overflow-y-auto"
        >
          <div class="flex flex-col gap-3" aria-label="Shown document fields">
            <label
              v-for="column in table
                .getAllLeafColumns()
                .filter(
                  (c) =>
                    c.getCanHide() &&
                    !DOCUMENT_ANNOTATION_GROUPS.some((g) =>
                      DOCUMENT_ANNOTATION_STATES.some(
                        (s) => annotationColumnId(g.scope, s.id) === c.id,
                      ),
                    ),
                )"
              :key="column.id"
              class="flex items-center gap-2"
            >
              <Checkbox
                :model-value="column.getIsVisible()"
                @update:model-value="column.toggleVisibility($event === true)"
              />
              {{ column.columnDef.header }}
            </label>
            <fieldset
              v-for="group in DOCUMENT_ANNOTATION_GROUPS"
              :key="group.id"
              class="flex flex-col gap-3"
            >
              <legend class="mb-3">{{ group.label }}</legend>
              <label
                v-for="column in table
                  .getAllLeafColumns()
                  .filter((c) =>
                    DOCUMENT_ANNOTATION_STATES.some(
                      (s) => annotationColumnId(group.scope, s.id) === c.id,
                    ),
                  )"
                :key="column.id"
                class="flex items-center gap-2"
              >
                <Checkbox
                  :aria-label="`${group.label}: ${annotationStateLabel(column.id)}`"
                  :model-value="column.getIsVisible()"
                  @update:model-value="column.toggleVisibility($event === true)"
                />
                {{ annotationStateLabel(column.id) }}
              </label>
            </fieldset>
            <Button variant="outline" @click="visibility = defaultDocumentColumns()"
              >Restore defaults</Button
            >
          </div>
        </PopoverContent>
      </Popover>
    </div>
    <p :id="`${tableId}-counts`" class="sr-only">
      Counts cover the entire registered document. All annotations combines faces and text mentions;
      each group includes total, automatic, manual, verified and unassigned counts. Pages counts
      registered pages only. Unknown means no recorded value.
    </p>
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
        :aria-describedby="`${tableId}-counts`"
        class="table-fixed caption-bottom text-sm"
        :style="{ width: `${table.getTotalSize()}px` }"
      >
        <colgroup>
          <col
            v-for="column in table.getVisibleLeafColumns()"
            :key="column.id"
            :data-column="column.id"
            :style="{ width: `${column.getSize()}px` }"
          />
        </colgroup>
        <TableHeader class="sticky top-0 z-10 bg-background">
          <TableRow v-for="group in table.getHeaderGroups()" :key="group.id">
            <TableHead
              v-for="header in group.headers.filter((h) => group.depth === 0 || h.column.parent)"
              :key="header.id"
              :id="columnHeaderId(header.column.id)"
              :colspan="header.colSpan"
              :rowspan="header.isPlaceholder ? table.getHeaderGroups().length : undefined"
              :scope="header.column.columns.length ? 'colgroup' : 'col'"
              :aria-sort="headerSort(header.column.id)"
              :style="{ width: `${header.getSize()}px` }"
              class="relative border-r pr-4 last:border-r-0"
            >
              <div class="flex items-center gap-1 py-2 whitespace-normal">
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
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="row in table.getRowModel().rows" :key="row.id">
            <TableCell
              v-for="cell in row.getVisibleCells()"
              :key="cell.id"
              :data-column="cell.column.id"
              class="border-r whitespace-normal last:border-r-0 [overflow-wrap:anywhere]"
              :style="{ width: `${cell.column.getSize()}px` }"
              :headers="
                cell.column.parent
                  ? `${columnHeaderId(cell.column.parent.id)} ${columnHeaderId(cell.column.id)}`
                  : columnHeaderId(cell.column.id)
              "
            >
              <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
            </TableCell>
          </TableRow>
          <TableRow v-if="loadingMore" data-slot="document-loading-row" aria-hidden="true">
            <TableCell
              v-for="column in table.getVisibleLeafColumns()"
              :key="column.id"
              :data-column="column.id"
              class="border-r last:border-r-0"
              :style="{ width: `${column.getSize()}px` }"
            >
              <Skeleton :class="column.id === 'first_page' ? 'h-28 w-20' : 'h-4 w-2/3'" />
            </TableCell>
          </TableRow>
        </TableBody>
      </table>
      <slot name="list-end" />
    </ScrollArea>
  </div>
</template>
