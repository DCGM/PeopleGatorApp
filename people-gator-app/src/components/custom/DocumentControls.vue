<script setup lang="ts">
import EntityLinkStateFilter from './EntityLinkStateFilter.vue'
import { scanToolbarButtonClass } from './scan-toolbar'
import type { EntityLinkState } from '@/client'
const linkStates = defineModel<EntityLinkState[]>('linkStates', { default: () => [] })
import { LocateFixed, Minus, Plus, Tags } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { ButtonGroup, ButtonGroupText } from '@/components/ui/button-group'

defineProps<{
  zoomPercent: number
  minimumZoomPercent: number
  maximumZoomPercent: number
  showBadgeNames: boolean
}>()

defineEmits<{
  'set-zoom': [direction: 'in' | 'out']
  'reset-view': []
  'toggle-badge-names': []
}>()
</script>

<template>
  <div role="toolbar" aria-label="Scan tools" class="flex select-none items-center gap-2">
    <ButtonGroup class="shrink-0">
      <Button
        variant="outline"
        :class="scanToolbarButtonClass"
        size="icon-sm"
        aria-label="Zoom out"
        title="Zoom out"
        :disabled="zoomPercent <= minimumZoomPercent"
        @click="$emit('set-zoom', 'out')"
      >
        <Minus />
      </Button>
      <ButtonGroupText class="min-w-14 justify-center px-2 font-mono">
        {{ zoomPercent }}%
      </ButtonGroupText>
      <Button
        variant="outline"
        :class="scanToolbarButtonClass"
        size="icon-sm"
        aria-label="Zoom in"
        title="Zoom in"
        :disabled="zoomPercent >= maximumZoomPercent"
        @click="$emit('set-zoom', 'in')"
      >
        <Plus />
      </Button>
      <Button
        variant="outline"
        :class="scanToolbarButtonClass"
        size="icon-sm"
        aria-label="Center page"
        title="Center page"
        @click="$emit('reset-view')"
      >
        <LocateFixed />
      </Button>
    </ButtonGroup>

    <ButtonGroup class="shrink-0">
      <Button
        variant="outline"
        :class="scanToolbarButtonClass"
        size="sm"
        :aria-label="showBadgeNames ? 'Hide overlay badge names' : 'Show overlay badge names'"
        :title="showBadgeNames ? 'Hide overlay badge names' : 'Show overlay badge names'"
        :aria-pressed="showBadgeNames"
        @click="$emit('toggle-badge-names')"
      >
        <Tags />
        Names
      </Button>
    </ButtonGroup>

    <EntityLinkStateFilter v-model="linkStates" toolbar />
  </div>
</template>
