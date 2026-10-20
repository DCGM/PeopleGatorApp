<script setup lang="ts">
import type { EntityLinkStats } from '@/client'
import { linkStates, linkStateVisuals } from '@/lib/entity-links'
import UiTooltip from './UiTooltip.vue'
defineProps<{ stats?: EntityLinkStats; unassigned?: boolean; layout?: 'compact' | 'person' }>()
const personTitles = { faces: 'Face annotations', mentions: 'Mention annotations' } as const
</script>
<template>
  <dl
    v-if="stats && layout === 'person'"
    class="mt-3 grid content-start gap-3"
    aria-label="Link statistics"
  >
    <div v-for="kind in ['faces', 'mentions'] as const" :key="kind">
      <dt class="text-muted-foreground">{{ personTitles[kind] }}</dt>
      <!-- Right-to-left item order only; each icon/value pair keeps its own reading order. -->
      <dd class="flex flex-row-reverse flex-wrap justify-between gap-x-3 font-mono">
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
            <component :is="linkStateVisuals[state].icon" class="size-3.5" aria-hidden="true" />{{
              stats[kind]?.[state] ?? 0
            }}
          </span>
        </UiTooltip>
      </dd>
    </div>
  </dl>
  <div v-else-if="stats" class="space-y-1 text-xs" aria-label="Link statistics">
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
