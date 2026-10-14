<script setup lang="ts">
import { ref } from 'vue'
import { Check, ChevronsUpDown } from '@lucide/vue'
import type { EntityLinkState } from '@/client'
import { linkStates, linkStateVisuals, parseLinkStates } from '@/lib/entity-links'
import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxTrigger,
  ComboboxList,
  ComboboxViewport,
  ComboboxGroup,
  ComboboxItem,
  ComboboxItemIndicator,
} from '@/components/ui/combobox'
import UiTooltip from './UiTooltip.vue'
defineProps<{ toolbar?: boolean }>()
const open = ref(false)
const selected = defineModel<EntityLinkState[]>({ default: () => [] })
function update(value: unknown) {
  selected.value = parseLinkStates(value)
}
function reset() {
  selected.value = []
  open.value = false
}
</script>
<template>
  <div
    v-if="toolbar"
    class="flex w-full flex-row flex-wrap items-center gap-2"
    aria-label="Link state"
  >
    <ToggleGroup
      type="multiple"
      :model-value="selected"
      variant="outline"
      size="sm"
      aria-label="Link state"
      @update:model-value="update"
    >
      <UiTooltip
        v-for="state in linkStates"
        :key="state"
        :text="linkStateVisuals[state].accessible"
      >
        <ToggleGroupItem :value="state" :aria-label="linkStateVisuals[state].label" class="gap-1">
          <component :is="linkStateVisuals[state].icon" class="size-3.5" aria-hidden="true" /><span
            class="hidden xl:inline"
            >{{ linkStateVisuals[state].label }}</span
          >
        </ToggleGroupItem>
      </UiTooltip>
    </ToggleGroup>
    <UiTooltip
      text="All includes unassigned annotations. Selecting all three states includes assigned annotations only."
    >
      <Button variant="outline" size="sm" :aria-pressed="selected.length === 0" @click="reset"
        >All</Button
      >
    </UiTooltip>
  </div>
  <Combobox
    v-else
    v-model:open="open"
    :model-value="selected"
    multiple
    ignore-filter
    @update:model-value="update"
  >
    <ComboboxAnchor class="w-auto max-w-full" as-child
      ><ComboboxTrigger as-child
        ><Button variant="outline" size="sm" aria-label="Link state" class="gap-2">
          {{ selected.length ? `Link state (${selected.length})` : 'All link states'
          }}<ChevronsUpDown class="size-3" aria-hidden="true" /> </Button></ComboboxTrigger
    ></ComboboxAnchor>
    <ComboboxList
      @escape-key-down="open = false"
      align="start"
      class="min-w-48"
      aria-label="Link state"
      ><ComboboxViewport
        ><ComboboxGroup>
          <ComboboxItem
            v-for="state in linkStates"
            :key="state"
            :value="state"
            :text-value="linkStateVisuals[state].label"
          >
            <component :is="linkStateVisuals[state].icon" class="size-3.5" aria-hidden="true" />{{
              linkStateVisuals[state].label
            }}
            <ComboboxItemIndicator
              ><Check class="size-4" aria-hidden="true"
            /></ComboboxItemIndicator>
          </ComboboxItem> </ComboboxGroup></ComboboxViewport
      ><Button variant="ghost" size="sm" class="w-full" @click="reset"
        >All link states</Button
      ></ComboboxList
    >
  </Combobox>
</template>
