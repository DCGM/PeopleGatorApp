<script setup lang="ts">
import { Clock, RefreshCw } from '@lucide/vue'
import { computed } from 'vue'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { PersonProcessingInfo } from '@/viewmodels/person-detail.types'

const props = defineProps<{
  processing: PersonProcessingInfo
  refreshing?: boolean
}>()

defineEmits<{ refresh: [] }>()

const timestamp = computed(() => {
  if (!props.processing.touchedAt) return null
  const date = new Date(props.processing.touchedAt)
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
  }).format(date)
})
</script>

<template>
  <Card class="mt-6 gap-3 py-4" aria-labelledby="processing-heading">
    <CardHeader class="flex flex-row items-center justify-between px-4">
      <CardTitle id="processing-heading" class="flex items-center gap-2 text-sm font-semibold">
        <Clock class="size-4 text-muted-foreground" aria-hidden="true" />
        Last processed
      </CardTitle>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Refresh processing information"
        title="Refresh processing information"
        :disabled="props.refreshing"
        @click="$emit('refresh')"
      >
        <RefreshCw class="size-4" :class="props.refreshing && 'animate-spin'" aria-hidden="true" />
      </Button>
    </CardHeader>
    <CardContent class="px-4 text-sm" aria-live="polite" :aria-busy="props.refreshing">
      <dl v-if="timestamp" class="grid gap-4 sm:grid-cols-3">
        <div class="min-w-0">
          <dt class="text-xs text-muted-foreground">Time</dt>
          <dd class="mt-1">
            <time
              :datetime="props.processing.touchedAt ?? undefined"
              :title="props.processing.touchedAt ?? undefined"
              >{{ timestamp }}</time
            >
          </dd>
        </div>
        <div class="min-w-0">
          <dt class="text-xs text-muted-foreground">User</dt>
          <dd class="mt-1 break-words" :title="props.processing.userId ?? undefined">
            {{ props.processing.userLabel || 'Unknown user' }}
          </dd>
        </div>
        <div class="min-w-0">
          <dt class="text-xs text-muted-foreground">API key</dt>
          <dd class="mt-1 break-words" :title="props.processing.apiKeyId ?? undefined">
            {{ props.processing.apiKeyLabel || 'No API key' }}
          </dd>
        </div>
      </dl>
      <div v-else>
        <p>No processing recorded</p>
        <p class="mt-1 text-xs text-muted-foreground">
          Older records may not have processing information.
        </p>
      </div>
    </CardContent>
  </Card>
</template>
