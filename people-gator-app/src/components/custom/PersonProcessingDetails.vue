<script setup lang="ts">
import { ChevronDown, Clock, RefreshCw } from '@lucide/vue'
import { computed, ref } from 'vue'

import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import type { PersonProcessingInfo } from '@/viewmodels/person-detail.types'

const props = defineProps<{
  processing: PersonProcessingInfo
  refreshing?: boolean
}>()

defineEmits<{ refresh: [] }>()

const expanded = ref(false)

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
  <Collapsible v-model:open="expanded" class="mt-4 border-t pt-3">
    <CollapsibleTrigger as-child>
      <Button
        variant="ghost"
        class="h-auto w-full justify-between gap-2 p-0 text-sm font-normal text-muted-foreground hover:bg-transparent hover:text-foreground has-[>svg]:px-0"
        :aria-label="expanded ? 'Hide processing information' : 'Show processing information'"
      >
        <span class="flex items-center gap-2">
          <Clock class="size-4" aria-hidden="true" />
          Last processed
        </span>
        <ChevronDown
          class="size-4 transition-transform"
          :class="expanded && 'rotate-180'"
          aria-hidden="true"
        />
      </Button>
    </CollapsibleTrigger>
    <CollapsibleContent class="space-y-3 pt-3 text-sm">
      <div aria-live="polite" :aria-busy="props.refreshing">
        <dl v-if="timestamp" class="grid gap-3">
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
      </div>
      <Button
        variant="ghost"
        size="sm"
        class="h-auto px-0 text-xs text-muted-foreground hover:bg-transparent hover:text-foreground has-[>svg]:px-0"
        aria-label="Refresh processing information"
        :disabled="props.refreshing"
        @click="$emit('refresh')"
      >
        <RefreshCw
          class="size-3.5"
          :class="props.refreshing && 'animate-spin'"
          aria-hidden="true"
        />
        Refresh
      </Button>
    </CollapsibleContent>
  </Collapsible>
</template>
