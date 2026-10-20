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
  <dl aria-label="Last change" class="mt-3 grid content-start gap-3">
    <div class="min-w-0">
      <dt class="text-muted-foreground">Last change</dt>
      <dd v-if="modified" class="font-mono text-lg">
        <time :datetime="props.processing.touchedAt ?? undefined" :title="exactTime">{{
          modified
        }}</time>
        <span class="sr-only">, exact time {{ exactTime }}</span>
      </dd>
      <dd v-else class="font-mono text-lg">Not recorded</dd>
    </div>
    <template v-if="modified">
      <div class="min-w-0">
        <dt class="text-muted-foreground">Modified by</dt>
        <dd class="font-mono text-lg break-words" :title="props.processing.userId ?? undefined">
          {{ props.processing.userLabel || 'Unknown user' }}
        </dd>
      </div>
      <div class="min-w-0">
        <dt class="text-muted-foreground">API key</dt>
        <dd class="font-mono text-lg break-words" :title="props.processing.apiKeyId ?? undefined">
          {{ props.processing.apiKeyLabel || 'No API key' }}
        </dd>
      </div>
    </template>
  </dl>
</template>
