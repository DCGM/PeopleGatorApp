<script setup lang="ts">
import { ref } from 'vue'

import CurrentFacePanel from '@/components/custom/CurrentFacePanel.vue'
import SimilarPeopleResults from '@/components/custom/SimilarPeopleResults.vue'
import SimilarPeopleSearch from '@/components/custom/SimilarPeopleSearch.vue'
import type { Face } from '@/viewmodels/document-workspace.types'
import type { SimilarPersonCandidate } from '@/viewmodels/similar-people.types'

const props = defineProps<{
  people: SimilarPersonCandidate[]
  selectedFace: Face | null
  viewedPersonId: string | null
  loading?: boolean
  assignmentPending?: boolean
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
}>()

const emit = defineEmits<{
  preview: [person: SimilarPersonCandidate]
  assign: [person: SimilarPersonCandidate]
  create: [person: SimilarPersonCandidate]
  unassign: []
  loadMore: []
}>()

const query = defineModel<string>('searchTerm', { default: '' })
const search = ref<InstanceType<typeof SimilarPeopleSearch> | null>(null)

function createPerson(profile: { name: string; shortDescription?: string }) {
  emit('create', {
    id: profile.name
      .toLocaleLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, ''),
    name: profile.name,
    shortDescription: profile.shortDescription,
    score: 100,
    nerMentions: 0,
    detections: 1,
    source: 'page',
  })
}

function focusSearch() {
  search.value?.focus()
}

defineExpose({ focusSearch })
</script>

<template>
  <section
    class="flex min-h-0 flex-1 flex-col gap-5 border-t p-5"
    aria-label="Face identity assignment"
  >
    <CurrentFacePanel
      :face="props.selectedFace"
      :assignment-pending="props.assignmentPending"
      @find-profile="focusSearch"
      @create="createPerson"
      @unassign="emit('unassign')"
    />
    <SimilarPeopleSearch ref="search" v-model="query" :selected-face="props.selectedFace" />
    <SimilarPeopleResults
      class="min-h-0 flex-1"
      :people="props.people"
      :selected-face="props.selectedFace"
      :viewed-person-id="props.viewedPersonId"
      :loading="props.loading"
      :assignment-pending="props.assignmentPending"
      :has-next-page="props.hasNextPage"
      :is-fetching-next-page="props.isFetchingNextPage"
      :search-term="query"
      @load-more="emit('loadMore')"
      @preview="emit('preview', $event)"
      @assign="emit('assign', $event)"
    />
  </section>
</template>
