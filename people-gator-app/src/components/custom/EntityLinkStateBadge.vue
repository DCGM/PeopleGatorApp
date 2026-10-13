<script setup lang="ts">
import { computed } from 'vue'
import type { LinkMetadata } from '@/lib/entity-links'
import { linkStateVisuals, linkTooltip } from '@/lib/entity-links'
import { Badge } from '@/components/ui/badge'
import UiTooltip from './UiTooltip.vue'
defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<LinkMetadata & { compact?: boolean; label?: string; focusable?: boolean }>(),
  { focusable: true },
)
const visual = computed(() => linkStateVisuals[props.linkState ?? 'unassigned'])
</script>
<template>
  <component
    :is="focusable ? UiTooltip : 'span'"
    :text="focusable ? linkTooltip(props) : undefined"
  >
    <Badge
      v-bind="$attrs"
      data-face-status-badge
      :tabindex="focusable === false ? undefined : 0"
      :aria-label="linkTooltip(props)"
      :title="linkTooltip(props)"
      class="border-0 font-normal focus-visible:outline-2 focus-visible:outline-ring"
      :class="[
        visual.classes,
        compact ? 'size-5 justify-center rounded-full p-0' : 'gap-1 px-2 py-0.5 text-xs',
        $attrs.class,
      ]"
    >
      <component :is="visual.icon" class="size-3 shrink-0" aria-hidden="true" />
      <span v-if="!compact" class="min-w-0 truncate">{{ label ?? visual.label }}</span>
    </Badge>
  </component>
</template>
