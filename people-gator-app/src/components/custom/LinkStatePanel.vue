<script setup lang="ts">
import { computed } from 'vue'
import type { EntityLinkState } from '@/client'
import { linkStateVisuals } from '@/lib/entity-links'
import SearchFilterPanel from './SearchFilterPanel.vue'
import EntityLinkStateFilter from './EntityLinkStateFilter.vue'
import ActiveFilters from './ActiveFilters.vue'
const selected = defineModel<EntityLinkState[]>({ default: () => [] })
const active = computed(() =>
  selected.value.map((value) => ({
    key: 'state',
    value,
    label: `Link state: ${linkStateVisuals[value].label}`,
  })),
)
</script>
<template>
  <SearchFilterPanel label="Link state" filters-only
    ><EntityLinkStateFilter v-model="selected"
  /></SearchFilterPanel>
  <ActiveFilters
    :filters="active"
    @remove="(chip) => (selected = selected.filter((state) => state !== chip.value))"
    @clear="selected = []"
  />
</template>
