<script setup lang="ts">
import { computed } from 'vue'
import { useNow } from '@vueuse/core'
import { BadgeCheck, CircleDashed } from '@lucide/vue'
import type { PageResponse } from '@/client'
import { Button } from '@/components/ui/button'
import { useCanAnnotate } from '@/composables/can-annotate'
import { annotationChangeTime } from '@/lib/annotation-change-time'
import { usePagePatchMutation } from '@/query/media'
import { usePeopleFilterOptions } from '@/query/people-filter-options'

// Page review state (#149). The document is verified once all its pages are.
const props = defineProps<{ page: PageResponse }>()
const allowed = useCanAnnotate()
const mutation = usePagePatchMutation()
const verified = computed(() => props.page.verification_state === 'verified')
const users = usePeopleFilterOptions(
  'user',
  '',
  computed(() => Boolean(props.page.verified_by_user_id)),
)
const now = useNow({ interval: 60_000 })
const verifier = computed(() => {
  const id = props.page.verified_by_user_id
  return id ? (users.labels.value[id] ?? id) : null
})
const when = computed(() => annotationChangeTime(props.page.verified_at, now.value))

function toggle() {
  mutation.mutate({
    sourceId: props.page.source_id,
    payload: { verification_state: verified.value ? 'not_verified' : 'verified' },
  })
}
</script>

<template>
  <div class="flex min-w-0 flex-wrap items-center gap-2" data-page-verification>
    <p class="flex min-w-0 flex-1 items-center gap-1.5 text-sm">
      <BadgeCheck v-if="verified" class="size-4 shrink-0" aria-hidden="true" />
      <CircleDashed v-else class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span class="min-w-0">
        <span class="font-medium">{{ verified ? 'Page verified' : 'Page not verified' }}</span>
        <small v-if="verified" class="block truncate text-muted-foreground"
          >{{ verifier ?? 'User not recorded'
          }}<template v-if="when">
            ·
            <time
              :datetime="page.verified_at ?? undefined"
              :title="new Date(page.verified_at!).toLocaleString()"
              >{{ when }}</time
            ></template
          ></small
        >
      </span>
    </p>
    <Button
      v-if="allowed"
      type="button"
      variant="outline"
      size="sm"
      :disabled="mutation.isPending.value"
      @click="toggle"
      >{{ verified ? 'Remove verification' : 'Verify page' }}</Button
    >
    <small v-if="mutation.isError.value" role="alert" class="basis-full"
      >Could not save verification.</small
    >
  </div>
</template>
