<script setup lang="ts">
import { Search, X } from '@lucide/vue'
import type { AcceptableValue } from 'reka-ui'
import { ref } from 'vue'

import type { Face } from '@/viewmodels/document-workspace.types'
import type { CandidateBrowseMode } from '@/viewmodels/similar-people'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

const props = defineProps<{
  selectedFace: Face | null
}>()

const query = defineModel<string>({ default: '' })
const resultMode = defineModel<CandidateBrowseMode>('resultMode', { default: 'page' })
const inputElement = ref<InstanceType<typeof InputGroupInput> | null>(null)

function updateResultMode(value: AcceptableValue | AcceptableValue[]) {
  if (value === 'page' || value === 'face') resultMode.value = value
}

function focus() {
  const input = inputElement.value?.$el as HTMLInputElement | undefined
  input?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  input?.focus()
}

function clear() {
  query.value = ''
}

defineExpose({ clear, focus })
</script>

<template>
  <section aria-labelledby="similar-people-search-title">
    <p id="similar-people-search-title" class="font-mono text-xs font-semibold uppercase text-secondary">
      {{ props.selectedFace?.personId ? 'Reassign to similar' : 'Assign to similar' }}
    </p>
    <ToggleGroup v-if="!query.trim()" type="single" variant="outline" size="sm"
      class="mt-2 grid w-full grid-cols-2 bg-card" :model-value="resultMode" aria-label="Choose candidate source"
      @update:model-value="updateResultMode">
      <ToggleGroupItem value="page" aria-label="Show people on this page">
        On this page
      </ToggleGroupItem>
      <ToggleGroupItem value="face" aria-label="Show people with similar faces"
        :disabled="!props.selectedFace?.embeddingModel">
        Similar faces
      </ToggleGroupItem>
    </ToggleGroup>
    <InputGroup class="mt-2 w-full bg-card">
      <InputGroupAddon align="inline-start">
        <Search aria-hidden="true" />
      </InputGroupAddon>
      <InputGroupInput ref="inputElement" v-model="query" placeholder="Search by name or alias"
        aria-label="Search people" :disabled="!props.selectedFace" />
      <InputGroupAddon align="inline-end">
        <InputGroupButton v-if="query" type="button" size="icon-sm" aria-label="Clear people search"
          @click="query = ''">
          <X aria-hidden="true" />
        </InputGroupButton>
      </InputGroupAddon>
    </InputGroup>
    <p v-if="
      props.selectedFace &&
      !props.selectedFace.embeddingModel &&
      !query.trim() &&
      resultMode === 'page'
    " class="mt-2 text-xs text-muted-foreground">
      Face similarity is unavailable for this detection. People on this page are shown instead.
    </p>
    <p v-else-if="query.trim()" class="mt-2 text-xs text-muted-foreground">
      Showing database name and alias matches.
    </p>
  </section>
</template>
