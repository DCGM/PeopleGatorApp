<script setup lang="ts">
import { computed } from 'vue'
import { useNow } from '@vueuse/core'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import { annotationChangeTime } from '@/lib/annotation-change-time'

const props = defineProps<{ touchedAt?: string | null; userId?: string | null }>()
const users = usePeopleFilterOptions(
  'user',
  '',
  computed(() => Boolean(props.userId)),
)
const now = useNow({ interval: 60_000 })
const userLabel = computed(() =>
  props.userId ? (users.labels.value[props.userId] ?? props.userId) : 'User not recorded',
)
const timestamp = computed(() => annotationChangeTime(props.touchedAt, now.value))
</script>

<template>
  <small class="block min-w-0 text-muted-foreground" aria-label="Annotation last changed">
    <span class="block"
      >Last changed
      <time
        v-if="timestamp"
        :datetime="touchedAt ?? undefined"
        :title="new Date(touchedAt!).toLocaleString()"
        >{{ timestamp }}</time
      ><span v-else>not recorded</span></span
    >
    <!-- TODO: Link the editor to their user tab once that tab is implemented. -->
    <span class="block truncate" :title="`Evidence changed by ${userLabel}`">{{ userLabel }}</span>
  </small>
</template>
