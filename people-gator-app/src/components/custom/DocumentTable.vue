<script setup lang="ts">
import { computed, h, useId } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  columnVisibilityFeature,
  tableFeatures,
  useTable,
  FlexRender,
  type ColumnDef,
  type ColumnVisibilityState,
} from '@tanstack/vue-table'
import { ArrowUp, ArrowDown } from '@lucide/vue'
import { defaultDirection, type SortState } from '@/lib/sorting'
import { DOCUMENT_BROWSE_DEFAULT } from '@/viewmodels/sort-options'
import type { DocumentResponse, DocumentSortField } from '@/client'
import DocumentFirstPage from './DocumentFirstPage.vue'
import DocumentSourceLink from './DocumentSourceLink.vue'
import { documentTitle } from '@/viewmodels/document-list'
import {
  annotationCount,
  annotationColumnId,
  DOCUMENT_ANNOTATION_GROUPS,
  DOCUMENT_ANNOTATION_STATES,
  defaultDocumentColumns,
  DOCUMENT_COLUMN_SORTS,
} from '@/viewmodels/document-table'
import { relatedQuery } from '@/viewmodels/shared-filters'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const tableId = useId()
const columnHeaderId = (id: string) => `${tableId}-${id}`

const props = defineProps<{ documents: DocumentResponse[] }>()
const visibility = defineModel<ColumnVisibilityState>('visibility', { required: true })
const sort = defineModel<SortState<DocumentSortField>>('sort', {
  default: () => ({ ...DOCUMENT_BROWSE_DEFAULT }),
})
function toggleSort(columnId: string) {
  const field = DOCUMENT_COLUMN_SORTS[columnId]
  if (!field) return
  sort.value = {
    field,
    direction:
      sort.value.field === field
        ? sort.value.direction === 'asc'
          ? 'desc'
          : 'asc'
        : defaultDirection(field),
  }
}
function headerSort(columnId: string) {
  return DOCUMENT_COLUMN_SORTS[columnId] === sort.value.field
    ? sort.value.direction === 'asc'
      ? 'ascending'
      : 'descending'
    : undefined
}
const route = useRoute()
const features = tableFeatures({ columnVisibilityFeature })
const link = (document: DocumentResponse, text: string) =>
  h(
    RouterLink,
    {
      to: { name: 'document-search', query: relatedQuery(route, { document: document.source_id }) },
      'aria-label': `Open ${documentTitle(document)} in ${document.library}, document ${document.document_id}`,
      class: 'underline underline-offset-4',
    },
    () => text,
  )
const columns: ColumnDef<typeof features, DocumentResponse>[] = [
  {
    id: 'identity',
    header: 'Document',
    enableHiding: false,
    cell: ({ row }) => link(row.original, `${row.original.library} · ${row.original.document_id}`),
  },
  {
    id: 'name',
    header: 'Document name',
    accessorFn: documentTitle,
    cell: ({ row }) => link(row.original, documentTitle(row.original)),
  },
  {
    id: 'ndk',
    header: 'NDK',
    cell: ({ row }) => h(DocumentSourceLink, { url: row.original.url }),
  },
  {
    id: 'first_page',
    header: 'First page',
    cell: ({ row }) => h(DocumentFirstPage, { document: row.original }),
  },
  { accessorKey: 'library', header: 'Library' },
  {
    accessorKey: 'document_id',
    header: 'Document ID',
    cell: ({ row }) => link(row.original, row.original.document_id),
  },
  {
    accessorKey: 'registered_page_count',
    header: 'Pages',
    cell: ({ getValue }) => getValue() ?? 'Unknown',
  },
  {
    id: 'last_modified',
    header: 'Last modified',
    accessorFn: (d) => d.last_touched_at,
    cell: ({ getValue }) =>
      getValue() ? new Date(String(getValue())).toLocaleString() : 'Unknown',
  },
  {
    id: 'modified_by',
    header: 'Modified by',
    accessorFn: (d) => d.last_touched_by_user_name || d.last_touched_by_user_id || 'Unknown',
  },
  {
    id: 'api_key',
    header: 'API key',
    accessorFn: (d) => d.last_touched_by_api_key_name || d.last_touched_by_api_key_id || '—',
  },
  ...DOCUMENT_ANNOTATION_GROUPS.map((group) => ({
    id: group.id,
    header: group.label,
    columns: DOCUMENT_ANNOTATION_STATES.map((state) => ({
      id: annotationColumnId(group.scope, state.id),
      header: state.label,
      accessorFn: (d: DocumentResponse) => annotationCount(d, state.id, group.scope),
      cell: ({ getValue }: { getValue: () => unknown }) => getValue() ?? 'Unknown',
    })),
  })),
  {
    accessorKey: 'linked_entity_count',
    header: 'Linked entities',
    cell: ({ getValue }) => getValue() ?? 'Unknown',
  },
]
const table = useTable({
  features,
  columns,
  data: computed(() => props.documents),
  getRowId: (row: DocumentResponse) => row.source_id,
  state: computed(() => ({
    columnVisibility: {
      ...visibility.value,
      identity: visibility.value.name === false && visibility.value.document_id !== true,
    },
  })),
  onColumnVisibilityChange: (next) => {
    visibility.value = typeof next === 'function' ? next(visibility.value) : next
  },
})
</script>

<template>
  <div class="flex min-w-0 flex-col gap-3">
    <div class="flex flex-wrap items-center gap-2">
      <Popover>
        <PopoverTrigger as-child><Button variant="outline">Columns</Button></PopoverTrigger>
        <PopoverContent
          align="start"
          class="max-h-[min(70dvh,var(--reka-popover-content-available-height))] overflow-y-auto"
        >
          <div class="flex flex-col gap-3" aria-label="Shown document fields">
            <label
              v-for="column in table.getAllLeafColumns().filter((c) => !c.parent && c.getCanHide())"
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
              v-for="group in table.getAllColumns().filter((c) => c.columns.length)"
              :key="group.id"
              class="flex flex-col gap-3"
            >
              <legend class="mb-3">{{ group.columnDef.header }}</legend>
              <label
                v-for="column in group.columns"
                :key="column.id"
                class="flex items-center gap-2"
              >
                <Checkbox
                  :aria-label="`${group.columnDef.header}: ${column.columnDef.header}`"
                  :model-value="column.getIsVisible()"
                  @update:model-value="column.toggleVisibility($event === true)"
                />
                {{ column.columnDef.header }}
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
    <div class="w-full min-w-0 max-w-full">
      <Table :aria-describedby="`${tableId}-counts`">
        <TableHeader>
          <TableRow v-for="group in table.getHeaderGroups()" :key="group.id">
            <TableHead
              v-for="header in group.headers.filter((h) => group.depth === 0 || h.column.parent)"
              :key="header.id"
              :id="columnHeaderId(header.column.id)"
              :colspan="header.colSpan"
              :rowspan="header.isPlaceholder ? table.getHeaderGroups().length : undefined"
              :scope="header.column.columns.length ? 'colgroup' : 'col'"
              :aria-sort="headerSort(header.column.id)"
            >
              <Button
                v-if="DOCUMENT_COLUMN_SORTS[header.column.id]"
                variant="ghost"
                size="sm"
                class="-ml-2.5"
                :aria-label="`Sort by ${header.column.columnDef.header}`"
                @click="toggleSort(header.column.id)"
              >
                <FlexRender :render="header.column.columnDef.header" :props="header.getContext()" />
                <ArrowUp v-if="headerSort(header.column.id) === 'ascending'" aria-hidden="true" />
                <ArrowDown
                  v-else-if="headerSort(header.column.id) === 'descending'"
                  aria-hidden="true"
                />
              </Button>
              <FlexRender
                v-else
                :render="header.column.columnDef.header"
                :props="header.getContext()"
              />
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="row in table.getRowModel().rows" :key="row.id">
            <TableCell
              v-for="cell in row.getVisibleCells()"
              :key="cell.id"
              :data-column="cell.column.id"
              :headers="
                cell.column.parent
                  ? `${columnHeaderId(cell.column.parent.id)} ${columnHeaderId(cell.column.id)}`
                  : columnHeaderId(cell.column.id)
              "
            >
              <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </div>
</template>
