<script setup lang="ts">
import { computed, h } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  columnVisibilityFeature,
  tableFeatures,
  useTable,
  FlexRender,
  type ColumnDef,
  type ColumnVisibilityState,
} from '@tanstack/vue-table'
import type { DocumentResponse } from '@/client'
import { documentTitle } from '@/viewmodels/document-list'
import { annotationCount, defaultDocumentColumns } from '@/viewmodels/document-table'
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

const props = defineProps<{ documents: DocumentResponse[] }>()
const visibility = defineModel<ColumnVisibilityState>('visibility', { required: true })
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
    id: 'open',
    header: 'Document',
    enableHiding: false,
    cell: ({ row }) =>
      link(
        row.original,
        visibility.value.name === false && visibility.value.document_id !== true
          ? `${row.original.library} · ${row.original.document_id}`
          : 'Open',
      ),
  },
  {
    id: 'name',
    header: 'Document name',
    accessorFn: documentTitle,
    cell: ({ row }) => link(row.original, documentTitle(row.original)),
  },
  { accessorKey: 'library', header: 'Library' },
  { accessorKey: 'document_id', header: 'Document ID' },
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
  ...(['total', 'automatic', 'verified', 'manual', 'unassigned'] as const).map((state) => ({
    id: state,
    header: {
      total: 'Annotations',
      automatic: 'Automatic',
      verified: 'Verified',
      manual: 'Manual',
      unassigned: 'Unassigned',
    }[state],
    accessorFn: (d: DocumentResponse) => annotationCount(d, state),
    cell: ({ getValue }: { getValue: () => unknown }) => getValue() ?? 'Unknown',
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
  state: computed(() => ({ columnVisibility: visibility.value })),
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
              v-for="column in table.getAllLeafColumns().filter((c) => c.getCanHide())"
              :key="column.id"
              class="flex items-center gap-2"
            >
              <Checkbox
                :model-value="column.getIsVisible()"
                @update:model-value="column.toggleVisibility($event === true)"
              />
              {{ column.columnDef.header }}
            </label>
            <Button variant="outline" @click="visibility = defaultDocumentColumns()"
              >Restore defaults</Button
            >
          </div>
        </PopoverContent>
      </Popover>
    </div>
    <p id="document-table-counts" class="sr-only">
      Counts cover the entire registered document. Annotations include unassigned faces and
      mentions. Pages counts registered pages only. Unknown means no recorded value.
    </p>
    <div class="w-full min-w-0 max-w-full">
      <Table aria-describedby="document-table-counts">
        <TableHeader>
          <TableRow v-for="group in table.getHeaderGroups()" :key="group.id">
            <TableHead v-for="header in group.headers" :key="header.id" scope="col">
              <FlexRender
                v-if="!header.isPlaceholder"
                :render="header.column.columnDef.header"
                :props="header.getContext()"
              />
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="row in table.getRowModel().rows" :key="row.id">
            <TableCell v-for="cell in row.getVisibleCells()" :key="cell.id">
              <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </div>
</template>
