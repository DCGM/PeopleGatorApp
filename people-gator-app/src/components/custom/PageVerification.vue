<script setup lang="ts">
import { computed } from 'vue'
import { useNow } from '@vueuse/core'
import type { PageResponse } from '@/client'
import { annotationChangeTime } from '@/lib/annotation-change-time'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import VerificationBadge from './VerificationBadge.vue'

// Page review state (#149); the Verify action lives in the top bar.
const props = defineProps<{ page: PageResponse }>()
const verified = computed(() => props.page.verification_state === 'verified')
const users = usePeopleFilterOptions(
  'user',
  '',
  computed(() => Boolean(props.page.verified_by_user_id)),
)
const now = useNow({ interval: 60_000 })
const verifier = computed(() => {
  const id = props.page.verified_by_user_id
  return id ? (users.labels.value[id] ?? id) : 'User not recorded'
})
const when = computed(() => annotationChangeTime(props.page.verified_at, now.value))
</script>

<template>
  <div class="flex min-w-0 flex-wrap items-center gap-2" data-page-verification>
    <VerificationBadge :state="page.verification_state" />
    <small v-if="verified" class="min-w-0 truncate text-muted-foreground"
      >{{ verifier
      }}<template v-if="when">
        ·
        <time
          :datetime="page.verified_at ?? undefined"
          :title="new Date(page.verified_at!).toLocaleString()"
          >{{ when }}</time
        ></template
      ></small
    >
  </div>
</template>
