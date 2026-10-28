<script setup lang="ts">
import { computed, ref } from 'vue'
import { X } from '@lucide/vue'
import type { EntityAnnotation } from '@/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import SearchFilterPanel from './SearchFilterPanel.vue'
import FilterMultiSelect from './FilterMultiSelect.vue'
import FilterSingleSelect from './FilterSingleSelect.vue'
const props = defineProps<{
  label: string
  searchable?: boolean
  resultCount?: number
  modelOptions?: { value: string; label: string }[]
  defaultFaceModel?: string
}>()
const emit = defineEmits<{ clearFilters: [] }>()
const searchTerm = defineModel<string>('searchTerm', { default: '' })
const annotations = defineModel<EntityAnnotation[]>('annotations', {
  default: () => ['faces', 'aliases', 'name'],
})
const faceModel = defineModel<string>('faceModel', { default: '' })
const inputSearch = ref('')
const labels = { faces: 'Faces', aliases: 'Aliases', name: 'Name' }
const inputOptions = computed(() =>
  Object.entries(labels)
    .map(([id, label]) => ({ id, label }))
    .filter((option) => option.label.toLowerCase().includes(inputSearch.value.toLowerCase())),
)
const selectedInputs = computed({
  get: () => annotations.value,
  set: (values: string[]) => {
    annotations.value = values.filter((value): value is EntityAnnotation => value in labels)
  },
})
const hasReferenceFilters = computed(
  () => annotations.value.length > 0 && annotations.value.length < 3,
)
const hasModelOverride = computed(() =>
  Boolean(faceModel.value && faceModel.value !== props.defaultFaceModel),
)
const modelLabel = computed(
  () =>
    props.modelOptions?.find((option) => option.value === faceModel.value)?.label ??
    faceModel.value,
)
</script>
<template>
  <div class="w-full min-w-0">
    <SearchFilterPanel
      v-model="searchTerm"
      :label="label"
      :filters-only="!searchable"
      placeholder="Search people"
      :result-count="resultCount"
    >
      <FilterMultiSelect
        v-model="selectedInputs"
        v-model:search="inputSearch"
        label="Modalities"
        :options="inputOptions"
      />
      <FilterSingleSelect
        v-if="modelOptions?.length"
        v-model="faceModel"
        label="Face model"
        :options="modelOptions"
      />
      <slot />
    </SearchFilterPanel>
    <div
      v-if="hasReferenceFilters || hasModelOverride"
      class="mt-3 flex min-w-0 flex-wrap items-center gap-2"
      :aria-label="`Active ${label.toLowerCase()} filters`"
    >
      <Badge
        v-for="input in hasReferenceFilters ? annotations : []"
        :key="input"
        as="small"
        variant="outline"
        class="max-w-full gap-1"
      >
        <span class="min-w-0 break-all">Modality: {{ labels[input] }}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          class="rounded-full"
          :aria-label="`Remove modality ${labels[input].toLowerCase()}`"
          @click="annotations = annotations.filter((item) => item !== input)"
          ><X aria-hidden="true"
        /></Button>
      </Badge>
      <Badge v-if="hasModelOverride" as="small" variant="outline" class="max-w-full gap-1">
        <span class="min-w-0 break-all">Face model: {{ modelLabel }}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          class="rounded-full"
          aria-label="Remove face model"
          @click="faceModel = ''"
          ><X aria-hidden="true"
        /></Button>
      </Badge>
      <Button type="button" variant="ghost" size="sm" @click="emit('clearFilters')"
        >Clear filters</Button
      >
    </div>
    <p v-if="!annotations.length && (!searchable || !searchTerm.trim())" role="status" class="mt-3">
      {{ searchable ? 'Choose a modality or enter search text.' : 'Choose a modality.' }}
    </p>
  </div>
</template>
