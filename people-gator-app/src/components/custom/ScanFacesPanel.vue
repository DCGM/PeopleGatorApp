<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import ActiveFilters, { type ActiveFilter } from './ActiveFilters.vue'
import FilterSingleSelect from './FilterSingleSelect.vue'
import ListPagination from './ListPagination.vue'
import ScanFaceThumbnail from './ScanFaceThumbnail.vue'
import SearchFilterPanel from './SearchFilterPanel.vue'
import SortControl from './SortControl.vue'
import { Button } from '@/components/ui/button'
import type { FaceSortField } from '@/client'
import type { SortState } from '@/lib/sorting'
import { WORKSPACE_FACE_SORTS } from '@/viewmodels/sort-options'
import type { ScanFaceGroup, ScanFaceItem } from '@/viewmodels/scan-faces'
import {
  EVIDENCE_SCOPES,
  FACE_VIEWS,
  type EvidenceScope,
  type FaceView,
} from '@/viewmodels/scan-sidebar'

const props = defineProps<{
  items: ScanFaceItem[]
  groups: ScanFaceGroup[]
  loading: boolean
  hasNextPage: boolean
  isFetching: boolean
  error?: unknown
  totalCount?: number
  selectedFaceId: string | null
  /** Evidence link-state filters narrow these faces too. */
  filtered?: boolean
  loadMore: () => Promise<unknown>
  retry: () => unknown
}>()
const scope = defineModel<EvidenceScope>('scope', { required: true })
const view = defineModel<FaceView>('view', { required: true })
const sort = defineModel<SortState<FaceSortField>>('sort', { required: true })
const emit = defineEmits<{ select: [faceId: string]; resetFilters: [] }>()
const route = useRoute()

const tags = computed<ActiveFilter[]>(() =>
  scope.value === 'page'
    ? []
    : [{ key: 'scope', value: scope.value, label: 'Scope: This document' }],
)
const sections = computed(() =>
  view.value === 'person'
    ? props.groups
    : [{ key: 'all', personId: null as string | null, items: props.items }],
)
function groupName(group: ScanFaceGroup) {
  if (!group.personId) return 'Unassigned'
  return group.items[0]?.personName ?? 'Linked person'
}
function location(item: ScanFaceItem) {
  const page = item.page
  if (item.onPage || !page) return undefined
  return {
    name: 'document-page',
    params: { libraryId: page.library, documentId: page.document_id, pageId: page.page_id },
    query: {
      ...route.query,
      person: item.face.detection_id,
      selectedPerson: item.face.entity_id ?? undefined,
      line: undefined,
    },
  }
}
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col" aria-label="Faces">
    <div class="shrink-0 px-3 pt-3">
      <SearchFilterPanel label="Faces" filters-only>
        <FilterSingleSelect v-model="scope" label="Scope" :options="EVIDENCE_SCOPES" />
        <FilterSingleSelect v-model="view" label="View" :options="FACE_VIEWS" />
        <SortControl
          v-if="view === 'flat'"
          v-model="sort"
          :options="WORKSPACE_FACE_SORTS"
          label="Sort faces"
        />
      </SearchFilterPanel>
      <ActiveFilters
        :filters="tags"
        clear-label="Clear filters"
        @remove="scope = 'page'"
        @clear="scope = 'page'"
      />
    </div>
    <div class="min-h-0 flex-1 overflow-y-auto px-3 pb-3 pt-3" :aria-busy="loading || isFetching">
      <p v-if="!loading" class="mb-2 text-xs text-muted-foreground" role="status">
        {{ totalCount ?? items.length }} {{ (totalCount ?? items.length) === 1 ? 'face' : 'faces' }}
      </p>
      <section
        v-for="group in sections"
        :key="group.key"
        class="mb-4 min-w-0"
        :aria-label="view === 'person' ? groupName(group) : 'Faces'"
      >
        <h3 v-if="view === 'person'" class="mb-2 truncate text-sm font-semibold">
          {{ groupName(group) }}
        </h3>
        <ul class="flex flex-row flex-wrap gap-3 p-1">
          <li v-for="item in group.items" :key="item.face.detection_id">
            <ScanFaceThumbnail
              :item="item"
              :selected="item.face.detection_id === selectedFaceId"
              :to="location(item)"
              @select="emit('select', item.face.detection_id)"
            />
          </li>
        </ul>
      </section>
      <div v-if="loading" class="size-16 animate-pulse rounded-md border bg-muted" role="status">
        <span class="sr-only">Loading faces</span>
      </div>
      <p
        v-else-if="!items.length && !hasNextPage && !error"
        class="py-6 text-center text-sm text-muted-foreground"
      >
        No faces.
        <Button v-if="filtered" type="button" variant="link" @click="emit('resetFilters')"
          >Reset filters</Button
        >
      </p>
      <ListPagination
        :has-next-page="hasNextPage"
        :is-fetching="isFetching"
        :error="error"
        error-text="Could not load faces."
        :reset-key="`${scope}:${view}:${sort.field}:${sort.direction}`"
        :load-more="loadMore"
        :retry="retry"
      />
    </div>
  </section>
</template>
