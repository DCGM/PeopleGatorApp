<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute, type LocationQuery } from 'vue-router'
import { BadgeCheck, ChevronDown, ChevronLeft, ChevronRight, CircleDashed } from '@lucide/vue'
import type { DocumentResponse, PageResponse } from '@/client'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useCanAnnotate } from '@/composables/can-annotate'
import { usePagePatchMutation } from '@/query/media'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import { useAdjacentPages } from '@/viewmodels/adjacent-pages'
import { GALLERY_NOT_VERIFIED_KEY, GALLERY_PERSON_KEY } from '@/viewmodels/gallery-person'
import { GALLERY_SORT_KEYS } from '@/viewmodels/sort-options'
import VerificationProgress from './VerificationProgress.vue'

// Page review in the top bar (#149): document progress, verify, previous/next page.
const props = defineProps<{ page: PageResponse; document?: DocumentResponse | null }>()
const route = useRoute()
const allowed = useCanAnnotate()
const mutation = usePagePatchMutation()
const verified = computed(() => props.page.verification_state === 'verified')
const users = usePeopleFilterOptions(
  'user',
  '',
  computed(() => Boolean(props.page.verified_by_user_id)),
)
const verifier = computed(() => {
  const id = props.page.verified_by_user_id
  return id ? (users.labels.value[id] ?? id) : 'User not recorded'
})
const adjacent = useAdjacentPages(
  () => props.page.library,
  () => props.page.document_id,
  () => props.page.page_id,
)

// Like the page strip: keep strip settings and the selected person, drop page selections.
const KEPT = [
  GALLERY_PERSON_KEY,
  GALLERY_NOT_VERIFIED_KEY,
  'selectedPerson',
  'panel',
  GALLERY_SORT_KEYS.field,
  GALLERY_SORT_KEYS.direction,
]
function location(target: PageResponse) {
  const query: LocationQuery = {}
  for (const key of KEPT) if (route.query[key] !== undefined) query[key] = route.query[key]!
  return {
    name: 'document-page',
    params: { libraryId: target.library, documentId: target.document_id, pageId: target.page_id },
    query,
  }
}
function save(state: 'verified' | 'not_verified') {
  mutation.mutate({ sourceId: props.page.source_id, payload: { verification_state: state } })
}
const verifiedClasses =
  'bg-emerald-600 text-white hover:bg-emerald-700 dark:bg-emerald-700 dark:hover:bg-emerald-600'
</script>

<template>
  <div class="flex shrink-0 items-center gap-1 sm:gap-2" role="group" aria-label="Page review">
    <!-- Phones keep only Verify and Next beside the breadcrumb. -->
    <span class="hidden sm:inline-flex">
      <VerificationProgress
        :verified="document?.verified_page_count"
        :total="document?.registered_page_count"
      />
    </span>
    <template v-if="allowed">
      <DropdownMenu v-if="verified">
        <DropdownMenuTrigger as-child>
          <Button
            type="button"
            size="sm"
            :class="verifiedClasses"
            :disabled="mutation.isPending.value"
            aria-label="Page verified, options"
            data-page-verify
          >
            <BadgeCheck aria-hidden="true" />
            <span class="hidden sm:inline">Verified</span>
            <ChevronDown class="hidden sm:block" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel class="font-normal text-muted-foreground">
            {{ verifier }} ·
            {{
              page.verified_at ? new Date(page.verified_at).toLocaleString() : 'time not recorded'
            }}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem @select="save('not_verified')">Remove verification</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Button
        v-else
        type="button"
        variant="outline"
        size="sm"
        class="text-emerald-700 dark:text-emerald-300"
        :disabled="mutation.isPending.value"
        aria-label="Verify page"
        data-page-verify
        @click="save('verified')"
      >
        <CircleDashed aria-hidden="true" />
        <span class="hidden sm:inline">Verify</span>
      </Button>
    </template>
    <span
      v-else
      class="inline-flex items-center gap-1 text-sm"
      :aria-label="verified ? 'Page verified' : 'Page not verified'"
    >
      <BadgeCheck v-if="verified" class="size-4 text-emerald-600" aria-hidden="true" />
      <CircleDashed v-else class="size-4 text-muted-foreground" aria-hidden="true" />
    </span>
    <span v-if="mutation.isError.value" role="alert" class="sr-only"
      >Could not save verification.</span
    >
    <div class="flex items-center">
      <Button
        v-if="adjacent.previous.value"
        variant="ghost"
        size="icon-sm"
        class="hidden sm:inline-flex"
        as-child
        aria-label="Previous page"
        title="Previous page"
      >
        <RouterLink :to="location(adjacent.previous.value)"
          ><ChevronLeft aria-hidden="true"
        /></RouterLink>
      </Button>
      <Button
        v-else
        variant="ghost"
        size="icon-sm"
        class="hidden sm:inline-flex"
        disabled
        aria-label="Previous page"
        ><ChevronLeft aria-hidden="true"
      /></Button>
      <Button
        v-if="adjacent.next.value"
        variant="ghost"
        size="icon-sm"
        as-child
        aria-label="Next page"
        title="Next page"
      >
        <RouterLink :to="location(adjacent.next.value)"
          ><ChevronRight aria-hidden="true"
        /></RouterLink>
      </Button>
      <Button v-else variant="ghost" size="icon-sm" disabled aria-label="Next page"
        ><ChevronRight aria-hidden="true"
      /></Button>
    </div>
  </div>
</template>
