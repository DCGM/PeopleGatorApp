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
    <RouterLink
      v-if="userId"
      :to="{ name: 'people-search', query: { evidence_user: userId } }"
      class="block truncate underline underline-offset-2"
      :title="`Evidence changed by ${userLabel}`"
      >{{ userLabel }}</RouterLink
    >
    <span v-else class="block">{{ userLabel }}</span>
  </small>
</template>
