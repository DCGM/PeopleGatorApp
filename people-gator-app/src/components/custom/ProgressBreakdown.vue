<script setup lang="ts">
import type { ProgressBreakdown, ProgressRow } from '@/lib/verification'

defineProps<{ breakdown: ProgressBreakdown }>()

// Mid tones stay legible on the tooltip's inverted surface in both themes.
const tones: Record<ProgressRow['tone'], { icon: string; bar: string }> = {
  verified: { icon: 'text-emerald-500', bar: 'bg-emerald-500' },
  manual: { icon: 'text-amber-500', bar: 'bg-amber-500' },
  automatic: { icon: 'text-sky-500', bar: 'bg-sky-500' },
  rest: { icon: 'opacity-60', bar: 'bg-background/25' },
}
const percent = (count: number, total: number) =>
  total ? `${Math.floor((count / total) * 100)}%` : '–'
</script>

<template>
  <div class="grid w-48 gap-2 py-1 text-left" data-progress-breakdown>
    <div class="flex items-center gap-1.5 font-medium">
      <component :is="breakdown.icon" class="size-3.5 shrink-0" aria-hidden="true" />
      <span>{{ breakdown.title }}</span>
      <span class="ml-auto tabular-nums">{{ breakdown.total }}</span>
    </div>
    <div class="flex h-1.5 gap-px overflow-hidden rounded-full bg-background/25" aria-hidden="true">
      <template v-for="row in breakdown.rows" :key="row.key">
        <span
          v-if="row.count && breakdown.total"
          :class="tones[row.tone].bar"
          :style="{ width: `${(row.count / breakdown.total) * 100}%` }"
        />
      </template>
    </div>
    <dl class="grid grid-cols-[auto_1fr_auto_auto] items-center gap-x-2 gap-y-1">
      <template v-for="row in breakdown.rows" :key="row.key">
        <component
          :is="row.icon"
          class="size-3.5"
          :class="tones[row.tone].icon"
          aria-hidden="true"
        />
        <dt>{{ row.label }}</dt>
        <dd class="text-right font-medium tabular-nums">{{ row.count }}</dd>
        <dd class="w-9 text-right tabular-nums opacity-60">
          {{ percent(row.count, breakdown.total) }}
        </dd>
      </template>
    </dl>
  </div>
</template>
