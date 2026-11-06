<script setup lang="ts">
import { computed, inject, ref, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { Info } from '@lucide/vue'
import type { EntityLinkState } from '@/client'
import AnnotationLastChange from './AnnotationLastChange.vue'
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { SCAN_SELECTED_MENTION, sidebarSettingsQuery } from '@/viewmodels/scan-sidebar'
import type { PersonMention } from '@/viewmodels/person-detail.types'
const props = defineProps<{
  mention: PersonMention
  /** Omitted where mentions of several people are listed; each links its own. */
  personId?: string
  linkStates: EntityLinkState[]
  compact?: boolean
}>()
const route = useRoute()
const onScan = computed(() => route.name === 'document-page')
const selectedOnScan = inject(SCAN_SELECTED_MENTION, null)
const selected = computed(() => selectedOnScan?.value === props.mention.id)
const samePage = computed(
  () =>
    route.params.libraryId === props.mention.library &&
    route.params.documentId === props.mention.documentId &&
    route.params.pageId === props.mention.pageId,
)
// The transcription's selection look: a muted line and a blue selected name.
const markClass = computed(() => [
  'text-secondary underline underline-offset-2',
  onScan.value && '-mx-0.5 px-0.5',
  selected.value ? 'bg-accent/20 outline-1 outline-accent' : 'bg-transparent',
])
// From a scan, the mention is selected there, on this page or another one,
// keeping the scan settings; elsewhere only the person is explicit context (#109).
const target = computed(() => ({
  name: 'document-page',
  params: {
    libraryId: props.mention.library,
    documentId: props.mention.documentId,
    pageId: props.mention.pageId,
  },
  query: {
    ...(onScan.value && {
      // The same page keeps every setting; another page keeps the sidebar's.
      ...(samePage.value ? route.query : sidebarSettingsQuery(route.query)),
      person: undefined,
      line: undefined,
      mention: props.mention.id,
    }),
    selectedPerson: props.personId ?? props.mention.metadata?.entity_id ?? undefined,
  },
}))
const infoOpen = ref(false)
let closeTimer: ReturnType<typeof setTimeout> | undefined
function openInfo() {
  clearTimeout(closeTimer)
  infoOpen.value = true
}
function closeInfo() {
  closeTimer = setTimeout(() => {
    infoOpen.value = false
  }, 150)
}
onBeforeUnmount(() => clearTimeout(closeTimer))
const parts = computed(() => {
  const index = props.mention.excerpt.indexOf(props.mention.matchedText)
  return index < 0
    ? null
    : [
        props.mention.excerpt.slice(0, index),
        props.mention.matchedText,
        props.mention.excerpt.slice(index + props.mention.matchedText.length),
      ]
})
</script>
<template>
  <div
    class="flex min-w-0 items-start gap-2 font-sans"
    :data-mention-selected="selected || undefined"
  >
    <div class="min-w-0 flex-1" :class="compact && 'flex flex-wrap items-center gap-x-2 gap-y-1'">
      <div class="flex min-w-0 items-center gap-2" :class="compact && 'max-w-full shrink-0'">
        <!-- On a scan only the mention text selects; its page is plain context. -->
        <span
          v-if="onScan && mention.pageId"
          class="min-w-0 text-sm text-muted-foreground wrap-anywhere"
          :title="`${mention.library} · ${mention.documentId} · ${mention.pageId}`"
          >{{ mention.pageLabel }}</span
        >
        <RouterLink
          v-else-if="mention.pageId"
          :to="target"
          class="min-w-0 text-sm underline wrap-anywhere"
          :title="`${mention.library} · ${mention.documentId} · ${mention.pageId}`"
        >
          {{
            compact
              ? mention.pageLabel
              : `${mention.library} · ${mention.documentTitle} · ${mention.pageLabel}`
          }}
        </RouterLink>
        <span v-else class="text-sm text-muted-foreground">{{
          mention.sourceLoading ? 'Loading source…' : 'Source unavailable'
        }}</span>
        <EntityLinkStateBadge v-bind="mention" class="shrink-0" />
      </div>
      <component
        :is="onScan && mention.pageId ? 'RouterLink' : 'p'"
        :to="onScan && mention.pageId ? target : undefined"
        class="block min-w-0 break-words font-serif"
        :class="[
          compact && 'basis-full truncate sm:basis-0 sm:flex-1',
          onScan &&
            'cursor-pointer rounded-sm px-1 text-muted-foreground hover:bg-muted/60 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring',
          selected && 'bg-muted text-foreground',
        ]"
        :title="mention.excerpt"
        :aria-label="onScan ? `Select mention: ${mention.excerpt}` : undefined"
        :aria-current="selected ? 'true' : undefined"
      >
        <template v-if="parts"
          >{{ parts[0] }}<mark :class="markClass">{{ parts[1] }}</mark
          >{{ parts[2] }}</template
        >
        <template v-else
          ><mark :class="markClass">{{ mention.matchedText }}</mark> ·
          {{ mention.excerpt }}</template
        >
      </component>
    </div>
    <Popover v-model:open="infoOpen">
      <PopoverTrigger as-child
        ><Button
          variant="ghost"
          size="icon-sm"
          @mouseenter="openInfo"
          @mouseleave="closeInfo"
          :aria-label="`Details for mention ${mention.id}`"
          ><Info class="size-4" aria-hidden="true" /></Button
      ></PopoverTrigger>
      <PopoverContent
        class="w-auto max-w-[calc(100vw-2rem)] break-words"
        @mouseenter="openInfo"
        @mouseleave="closeInfo"
        @open-auto-focus.prevent
      >
        <AnnotationLastChange
          :touched-at="mention.metadata?.last_touched_at"
          :user-id="mention.metadata?.last_touched_by_user_id"
        />
      </PopoverContent>
    </Popover>
  </div>
</template>
