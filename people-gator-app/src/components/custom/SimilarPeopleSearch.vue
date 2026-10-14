<script setup lang="ts">
import type { AcceptableValue } from 'reka-ui'
import { computed, ref } from 'vue'
import SearchFilterPanel from './SearchFilterPanel.vue'
import ActiveFilters from './ActiveFilters.vue'

import type { Face } from '@/viewmodels/document-workspace.types'
import type { CandidateBrowseMode } from '@/viewmodels/similar-people'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

const props = defineProps<{
  selectedFace: Face | null
}>()

const query = defineModel<string>({ default: '' })
const resultMode = defineModel<CandidateBrowseMode>('resultMode', { default: 'page' })
const inputElement = ref<InstanceType<typeof SearchFilterPanel> | null>(null)

function updateResultMode(value: AcceptableValue | AcceptableValue[]) {
  if (value === 'page' || value === 'face') resultMode.value = value
}

function focus() {
  inputElement.value?.focus()
}

function clear() {
  query.value = ''
}

defineExpose({ clear, focus })
const active = computed(() =>
  !query.value.trim() && resultMode.value === 'face'
    ? [{ key: 'source', value: 'face', label: 'Candidate source: Similar faces' }]
    : [],
)
</script>

<template>
  <section aria-labelledby="similar-people-search-title">
    <p
      id="similar-people-search-title"
      class="font-mono text-xs font-semibold uppercase text-secondary"
    >
      {{ props.selectedFace?.personId ? 'Reassign to similar' : 'Assign to similar' }}
    </p>
    <SearchFilterPanel
      ref="inputElement"
      v-model="query"
      class="mt-2"
      label="Search people"
      placeholder="Search by name or alias"
      :hide-filters="!!query.trim()"
      :disabled="!props.selectedFace"
    >
      <ToggleGroup
        v-if="!query.trim()"
        type="single"
        variant="outline"
        size="sm"
        :model-value="resultMode"
        aria-label="Choose candidate source"
        @update:model-value="updateResultMode"
      >
        <ToggleGroupItem value="page" aria-label="Show people on this page"
          >On this page</ToggleGroupItem
        >
        <ToggleGroupItem
          value="face"
          aria-label="Show people with similar faces"
          :disabled="!props.selectedFace?.embeddingModel"
          >Similar faces</ToggleGroupItem
        >
      </ToggleGroup>
    </SearchFilterPanel>
    <ActiveFilters :filters="active" @remove="resultMode = 'page'" @clear="resultMode = 'page'" />
    <p
      v-if="
        props.selectedFace &&
        !props.selectedFace.embeddingModel &&
        !query.trim() &&
        resultMode === 'page'
      "
      class="mt-2 text-xs text-muted-foreground"
    >
      Face similarity is unavailable for this detection. People on this page are shown instead.
    </p>
    <p v-else-if="query.trim()" class="mt-2 text-xs text-muted-foreground">
      Showing database name and alias matches.
    </p>
  </section>
</template>
