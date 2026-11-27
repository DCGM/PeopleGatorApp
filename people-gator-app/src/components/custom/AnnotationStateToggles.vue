<script setup lang="ts">
import { linkStateVisuals } from '@/lib/entity-links'
import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { scanToolbarButtonClass } from './scan-toolbar'
import { annotationStates, parseAnnotationStates, type AnnotationState } from '@/lib/entity-links'

// The state toggles of the scan toolbar (faces) and the transcription (mentions).
// No state pressed is All; the states combine as a union.
withDefaults(defineProps<{ label?: string; groupLabel?: string }>(), {
  label: 'Annotation states',
  groupLabel: 'Annotation state controls',
})
const selected = defineModel<AnnotationState[]>({ default: () => [] })
function update(value: unknown) {
  selected.value = parseAnnotationStates(value)
}
</script>

<template>
  <ButtonGroup class="shrink-0" :aria-label="groupLabel">
    <ToggleGroup
      type="multiple"
      :model-value="selected"
      variant="outline"
      size="sm"
      :aria-label="label"
      @update:model-value="update"
    >
      <ToggleGroupItem
        v-for="state in annotationStates"
        :key="state"
        :value="state"
        :aria-label="linkStateVisuals[state].label"
        :title="linkStateVisuals[state].accessible"
        :class="[scanToolbarButtonClass, 'gap-1 px-2']"
      >
        <component :is="linkStateVisuals[state].icon" class="size-3.5" aria-hidden="true" />
        <span class="hidden @3xl:inline">{{ linkStateVisuals[state].label }}</span>
      </ToggleGroupItem>
    </ToggleGroup>
    <Button
      variant="outline"
      :class="scanToolbarButtonClass"
      size="sm"
      :aria-pressed="selected.length === 0"
      @click="selected = []"
      >All</Button
    >
  </ButtonGroup>
</template>
