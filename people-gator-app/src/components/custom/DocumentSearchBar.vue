<script setup lang="ts">
import EntityLinkStateFilter from './EntityLinkStateFilter.vue'
import type { EntityLinkState } from '@/client'
const linkStates = defineModel<EntityLinkState[]>('linkStates', { default: () => [] })
import { computed } from 'vue'
import SearchFilterPanel from './SearchFilterPanel.vue'
import ActiveFilters from './ActiveFilters.vue'
import { linkStateVisuals } from '@/lib/entity-links'

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { PageContentFilter } from '@/viewmodels/assignment'

defineProps<{
  resultCount: number
  hasMoreResults?: boolean
}>()

const searchTerm = defineModel<string>('searchTerm', { required: true })
const assignment = defineModel<PageContentFilter>('assignment', { required: true })
const active = computed(() => [
  ...(assignment.value === 'all'
    ? []
    : [{ key: 'assignment', value: assignment.value, label: `Page content: ${assignment.value}` }]),
  ...linkStates.value.map((value) => ({
    key: 'state',
    value,
    label: `Link state: ${linkStateVisuals[value].label}`,
  })),
])
function remove(chip: { key: string; value: string }) {
  if (chip.key === 'assignment') assignment.value = 'all'
  else linkStates.value = linkStates.value.filter((state) => state !== chip.value)
}
function clear() {
  assignment.value = 'all'
  linkStates.value = []
}
</script>

<template>
  <SearchFilterPanel
    v-model="searchTerm"
    label="Search scans"
    placeholder="Search a person, page or document…"
    :result-count="resultCount"
    :has-more-results="hasMoreResults"
  >
    <EntityLinkStateFilter v-model="linkStates" />
    <div class="min-w-0 flex-1 basis-40">
      <Select v-model="assignment"
        ><SelectTrigger class="w-full" aria-label="Page content"
          ><SelectValue placeholder="Page content" /></SelectTrigger
        ><SelectContent
          ><SelectGroup
            ><SelectLabel>Page content</SelectLabel><SelectItem value="all">All pages</SelectItem
            ><SelectItem value="entities">Contains assigned entities</SelectItem
            ><SelectItem value="faces">Contains faces</SelectItem
            ><SelectItem value="mentions">Contains mentions</SelectItem></SelectGroup
          ></SelectContent
        ></Select
      >
    </div>
  </SearchFilterPanel>
  <ActiveFilters :filters="active" @remove="remove" @clear="clear" />
</template>
