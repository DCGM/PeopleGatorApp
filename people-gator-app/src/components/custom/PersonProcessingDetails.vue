<script setup lang="ts">
import { computed } from 'vue'

import { useNow } from '@/composables/now'
import { lastChangeLabel } from '@/lib/annotation-change-time'
import type { PersonProcessingInfo } from '@/viewmodels/person-detail.types'

const props = defineProps<{ processing: PersonProcessingInfo }>()

const now = useNow()
const modified = computed(() => lastChangeLabel(props.processing.touchedAt, now.value))
const exactTime = computed(() => {
  if (!props.processing.touchedAt) return undefined
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'long',
  }).format(new Date(props.processing.touchedAt))
})
</script>

<template>
  <section aria-labelledby="person-last-change" class="mt-4 border-t pt-3">
    <h3 id="person-last-change" class="text-muted-foreground">Last change</h3>
    <template v-if="modified">
      <p class="font-mono text-lg">
        <time :datetime="props.processing.touchedAt ?? undefined" :title="exactTime">{{
          modified
        }}</time>
      </p>
      <span class="sr-only">Exact time: {{ exactTime }}</span>
      <dl class="mt-3 grid gap-3">
        <div class="min-w-0">
          <dt class="text-muted-foreground">Modified by</dt>
          <dd class="break-words font-mono" :title="props.processing.userId ?? undefined">
            {{ props.processing.userLabel || 'Unknown user' }}
          </dd>
        </div>
        <div class="min-w-0">
          <dt class="text-muted-foreground">API key</dt>
          <dd class="break-words font-mono" :title="props.processing.apiKeyId ?? undefined">
            {{ props.processing.apiKeyLabel || 'No API key' }}
          </dd>
        </div>
      </dl>
    </template>
    <template v-else>
      <p class="font-mono text-lg">Not recorded</p>
      <p class="mt-1 text-xs text-muted-foreground">
        Older records may not have change information.
      </p>
    </template>
  </section>
</template>
