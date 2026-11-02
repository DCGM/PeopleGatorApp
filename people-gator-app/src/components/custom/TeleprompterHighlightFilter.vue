<script setup lang="ts">
import { linkStateVisuals } from '@/lib/entity-links'
import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { scanToolbarButtonClass } from './scan-toolbar'
import {
  HIGHLIGHT_STATES,
  parseHighlightStates,
  type HighlightState,
} from '@/viewmodels/teleprompter'

// Mirrors the scan toolbar's link-state toggle group, plus Unassigned. The chosen
// states highlight annotations and narrow Annotated and Person lines.
const selected = defineModel<HighlightState[]>({ default: () => [] })
function update(value: unknown) {
  selected.value = parseHighlightStates(value)
}
</script>

<template>
  <ButtonGroup class="shrink-0" aria-label="Annotation state controls">
    <ToggleGroup
      type="multiple"
      :model-value="selected"
      variant="outline"
      size="sm"
      aria-label="Annotation states"
      @update:model-value="update"
    >
      <ToggleGroupItem
        v-for="state in HIGHLIGHT_STATES"
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
