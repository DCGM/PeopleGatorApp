<script setup lang="ts">
import { useRoute } from 'vue-router'
import type { EntityLinkState } from '@/client'
import CreationDetails from './CreationDetails.vue'
import PersonMentionItem from './PersonMentionItem.vue'
import VerifyEntityLink from './VerifyEntityLink.vue'
import { relatedEvidenceQuery } from '@/viewmodels/evidence-filters'
import type { PersonMention } from '@/viewmodels/person-detail.types'

defineProps<{ mention: PersonMention; personId: string; linkStates: EntityLinkState[] }>()
const route = useRoute()
</script>

<template>
  <div>
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
          ...relatedEvidenceQuery(route),
          selectedPerson: personId,
          ...(linkStates.length && { link_state: linkStates }),
        },
      }"
      class="group block py-6 outline-none"
    >
      <PersonMentionItem :mention="mention" />
    </RouterLink>
    <p v-if="!mention.pageId">
      {{ mention.excerpt }} ·
      {{ mention.sourceLoading ? 'Loading source page…' : 'Source page unavailable.' }}
    </p>
    <CreationDetails
      v-if="mention.metadata"
      :record="mention.metadata"
      label="Mention creation / import"
    />
    <VerifyEntityLink v-bind="mention" :id="mention.id" kind="mention" />
  </div>
</template>
