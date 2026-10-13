<script setup lang="ts">
import type { EntityLinkStats } from '@/client'
import { linkStates, linkStateVisuals } from '@/lib/entity-links'
import UiTooltip from './UiTooltip.vue'
defineProps<{ stats?: EntityLinkStats; unassigned?: boolean }>()
</script>
<template>
  <div v-if="stats" class="space-y-1 text-xs" aria-label="Link statistics">
    <div
      v-for="kind in ['faces', 'mentions'] as const"
      :key="kind"
      class="flex flex-wrap items-center gap-x-3 gap-y-1"
    >
      <span class="w-16 font-semibold capitalize">{{ kind }}</span>
      <UiTooltip
        v-for="state in linkStates"
        :key="state"
        :text="`${linkStateVisuals[state].label}: ${stats[kind]?.[state] ?? 0} ${kind}`"
      >
        <span
          tabindex="0"
          class="inline-flex items-center gap-1"
          :aria-label="`${linkStateVisuals[state].label}: ${stats[kind]?.[state] ?? 0} ${kind}`"
        >
          <component :is="linkStateVisuals[state].icon" class="size-3" aria-hidden="true" />{{
            stats[kind]?.[state] ?? 0
          }}
        </span>
      </UiTooltip>
      <span v-if="unassigned" class="inline-flex items-center gap-1"
        ><component
          :is="linkStateVisuals.unassigned.icon"
          class="size-3"
          aria-hidden="true"
        />Unassigned {{ stats[kind]?.unassigned ?? 0 }}</span
      >
      <span class="text-muted-foreground">Total {{ stats[kind]?.total ?? 0 }}</span>
    </div>
  </div>
</template>
