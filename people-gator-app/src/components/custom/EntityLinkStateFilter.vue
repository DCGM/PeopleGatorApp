<script setup lang="ts">
import { ref } from 'vue'
import { Check, ChevronsUpDown } from '@lucide/vue'
import type { EntityLinkState } from '@/client'
import { linkStates, linkStateVisuals, parseLinkStates } from '@/lib/entity-links'
import { Button, buttonVariants } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
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
  <ButtonGroup v-if="toolbar" class="shrink-0" aria-label="Link state controls">
    <ToggleGroup
      type="multiple"
      :model-value="selected"
      variant="outline"
      size="sm"
      aria-label="Link state"
      @update:model-value="update"
    >
      <ToggleGroupItem
        v-for="state in linkStates"
        :key="state"
        :value="state"
        :aria-label="linkStateVisuals[state].label"
        :title="linkStateVisuals[state].accessible"
        :class="[buttonVariants({ variant: 'secondary', size: 'sm' }), 'gap-1']"
      >
        <component :is="linkStateVisuals[state].icon" class="size-3.5" aria-hidden="true" />
        <span class="hidden xl:inline">{{ linkStateVisuals[state].label }}</span>
      </ToggleGroupItem>
    </ToggleGroup>
    <UiTooltip
      text="All includes unassigned annotations. Selecting all three states includes assigned annotations only."
    >
      <Button
        :variant="selected.length === 0 ? 'default' : 'secondary'"
        size="sm"
        :aria-pressed="selected.length === 0"
        @click="reset"
        >All</Button
      >
    </UiTooltip>
  </ButtonGroup>
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
        ><Button variant="outline" aria-label="Link state" class="gap-2">
          {{ selected.length ? `Link state (${selected.length})` : 'All link states'
          }}<ChevronsUpDown class="size-4 shrink-0" aria-hidden="true" /> </Button></ComboboxTrigger
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
