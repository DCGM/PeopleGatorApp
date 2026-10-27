<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import type { EntityLinkState } from '@/client'
import CreationDetails from './CreationDetails.vue'
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
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
  <div>
    <div class="flex min-w-0 items-center gap-2">
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
        {{ compact ? mention.pageLabel : `${mention.documentTitle} · ${mention.pageLabel}` }}
      </RouterLink>
      <span v-else class="text-sm text-muted-foreground">{{
        mention.sourceLoading ? 'Loading source…' : 'Source unavailable'
      }}</span>
      <EntityLinkStateBadge v-bind="mention" class="shrink-0" />
    </div>
    <p :class="compact && 'truncate'" :title="mention.excerpt" class="min-w-0 break-words">
      <template v-if="parts"
        >{{ parts[0] }}<mark>{{ parts[1] }}</mark
        >{{ parts[2] }}</template
      >
      <template v-else
        ><mark>{{ mention.matchedText }}</mark> · {{ mention.excerpt }}</template
      >
    </p>
    <details class="text-sm">
      <summary>Details</summary>
      <p v-if="compact" class="break-words">{{ mention.excerpt }}</p>
      <CreationDetails
        v-if="mention.metadata"
        :record="mention.metadata"
        label="Creation / import"
      />
    </details>
  </div>
</template>
