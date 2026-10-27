<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Ellipsis } from '@lucide/vue'
import type { EntityLinkState } from '@/client'
import CreationDetails from './CreationDetails.vue'
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { relatedQuery } from '@/viewmodels/shared-filters'
import type { PersonMention } from '@/viewmodels/person-detail.types'
const props = defineProps<{
  mention: PersonMention
  personId: string
  linkStates: EntityLinkState[]
  compact?: boolean
}>()
const route = useRoute()
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
  <div class="flex min-w-0 items-start gap-2">
    <div class="min-w-0 flex-1" :class="compact && 'flex flex-wrap items-center gap-x-2 gap-y-1'">
      <div class="flex min-w-0 items-center gap-2" :class="compact && 'max-w-full shrink-0'">
        <RouterLink
          v-if="mention.pageId"
          :to="{
            name: 'document-page',
            params: {
              libraryId: mention.library,
              documentId: mention.documentId,
              pageId: mention.pageId,
            },
            query: {
              ...relatedQuery(route),
              selectedPerson: personId,
              ...(linkStates.length && { link_state: linkStates }),
            },
          }"
          class="min-w-0 truncate text-sm underline"
          :title="`${mention.library} · ${mention.documentId} · ${mention.pageId}`"
        >
          {{
            compact
              ? mention.pageLabel.slice(0, 8)
              : `${mention.documentTitle} · ${mention.pageLabel.slice(0, 8)}`
          }}
        </RouterLink>
        <span v-else class="text-sm text-muted-foreground">{{
          mention.sourceLoading ? 'Loading source…' : 'Source unavailable'
        }}</span>
        <EntityLinkStateBadge v-bind="mention" class="shrink-0" />
      </div>
      <p
        class="min-w-0 break-words"
        :class="compact && 'basis-full truncate sm:basis-0 sm:flex-1'"
        :title="mention.excerpt"
      >
        <template v-if="parts"
          >{{ parts[0] }}<mark>{{ parts[1] }}</mark
          >{{ parts[2] }}</template
        >
        <template v-else
          ><mark>{{ mention.matchedText }}</mark> · {{ mention.excerpt }}</template
        >
      </p>
    </div>
    <Popover>
      <PopoverTrigger as-child
        ><Button variant="ghost" size="icon-sm" :aria-label="`Details for mention ${mention.id}`"
          ><Ellipsis class="size-4" aria-hidden="true" /></Button
      ></PopoverTrigger>
      <PopoverContent class="max-w-[calc(100vw-2rem)] space-y-3 break-words">
        <p>{{ mention.excerpt }}</p>
        <CreationDetails
          v-if="mention.metadata"
          :record="mention.metadata"
          label="Creation / import"
        />
      </PopoverContent>
    </Popover>
  </div>
</template>
