<script setup lang="ts">
import { Image, ScanFace, UserRoundSearch } from '@lucide/vue'
import { useDebounce } from '@vueuse/core'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PersonEditableDetails from '@/components/custom/PersonEditableDetails.vue'
import PersonProcessingDetails from '@/components/custom/PersonProcessingDetails.vue'
import PersonDiscoveryPanel from '@/components/custom/PersonDiscoveryPanel.vue'
import PersonFaceCard from '@/components/custom/PersonFaceCard.vue'
import PersonFaceCardSkeleton from '@/components/custom/PersonFaceCardSkeleton.vue'
import PersonMentionItem from '@/components/custom/PersonMentionItem.vue'
import PersonMentionItemSkeleton from '@/components/custom/PersonMentionItemSkeleton.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { usePersonDiscovery } from '@/viewmodels/person-discovery'
import { usePersonDetail } from '@/viewmodels/person-detail'

const route = useRoute()
const router = useRouter()
const personId = computed(() => String(route.params.personId))

const {
  entity,
  error,
  faceEmbeddingModel,
  faceCount,
  faceIds,
  faces,
  identifiers,
  isLoading,
  libraryCount,
  mentionCount,
  mentions,
  portrait,
  portraitLoading,
  profile,
  processing,
  processingRefreshing,
  refreshProcessing,
  updateIdentifiers,
  updateProfile,
} = usePersonDetail(personId)

const activeTab = computed(() => {
  if (route.query.tab === 'mentions') return 'mentions'
  if (route.query.tab === 'discover') return 'discover'
  return 'faces'
})
const personSearchTerm = ref('')
const debouncedPersonSearchTerm = useDebounce(personSearchTerm, 300)
let searchSeeded = false
let lastSeededName = ''

watch(personId, () => {
  const currentName = profile.value.name
  const canSeed = Boolean(currentName && currentName !== 'Unnamed person')
  personSearchTerm.value = canSeed ? currentName : ''
  searchSeeded = canSeed
  lastSeededName = canSeed ? currentName : ''
})

watch(
  () => profile.value.name,
  (name) => {
    if (!name || name === 'Unnamed person') return
    if (searchSeeded && personSearchTerm.value !== lastSeededName) return
    personSearchTerm.value = name
    searchSeeded = true
    lastSeededName = name
  },
  { immediate: true },
)

const {
  assignFaces,
  assignmentStatus,
  error: discoveryError,
  isLoadingFaces,
  isLoadingPeople,
  mergePeople,
  mergeStatus,
  similarFaces,
  similarPeople,
} = usePersonDiscovery(
  personId,
  faceIds,
  faceEmbeddingModel,
  debouncedPersonSearchTerm,
  computed(() => activeTab.value === 'discover'),
)

function selectTab(tab: string | number) {
  const selectedTab = tab === 'mentions' || tab === 'discover' ? tab : 'faces'
  void router.replace({
    name: 'person-detail',
    params: { personId: personId.value },
    query: selectedTab === 'faces' ? {} : { tab: selectedTab },
  })
}
</script>

<template>
  <main class="mx-auto w-full max-w-6xl px-4 pb-12 pt-7 sm:px-6">
    <p v-if="error" class="py-16 text-center text-destructive">Could not load this person.</p>
    <template v-else>
      <PersonEditableDetails
        :model-value="profile"
        :person-id="personId"
        :portrait="portrait"
        :portrait-loading="portraitLoading"
        :face-count="faceCount"
        :mention-count="mentionCount"
        :library-count="libraryCount"
        :wikidata-id="identifiers.wikidataId"
        :national-library-authority-id="identifiers.nationalLibraryAuthorityId"
        @update:model-value="updateProfile"
        @update:identifiers="updateIdentifiers"
      >
        <template #statistics>
          <PersonProcessingDetails
            v-if="entity"
            :key="personId"
            :processing="processing"
            :refreshing="processingRefreshing"
            @refresh="refreshProcessing"
          />
        </template>
      </PersonEditableDetails>

      <Tabs :model-value="activeTab" class="mt-8" @update:model-value="selectTab">
        <h2>Evidence and identity discovery</h2>
        <TabsList aria-label="Person record sections" class="gap-2 mt-4">
          <TabsTrigger value="faces">
            <ScanFace class="size-4" aria-hidden="true" /> Faces
            <span class="font-mono">{{ faceCount }}</span>
          </TabsTrigger>
          <TabsTrigger value="mentions">
            <Image class="size-4" aria-hidden="true" /> Mentions
            <span class="font-mono">{{ mentionCount }}</span>
          </TabsTrigger>
          <TabsTrigger value="discover">
            <UserRoundSearch class="size-4" aria-hidden="true" /> Discover
          </TabsTrigger>
        </TabsList>

        <TabsContent
          value="faces"
          class="grid grid-cols-2 gap-4 pt-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6"
        >
          <RouterLink
            :to="{
              name: 'document-page',
              params: { libraryId: face.library, documentId: face.documentId, pageId: face.pageId },
              query: { person: face.id },
            }"
            v-for="face in faces"
            :key="face.id"
            class="group"
          >
            <PersonFaceCard :face="face" :person-name="profile.name" />
          </RouterLink>
          <PersonFaceCardSkeleton v-if="isLoading" />
        </TabsContent>

        <TabsContent value="mentions" class="divide-y">
          <RouterLink
            v-for="mention in mentions"
            :key="mention.id"
            :to="{
              name: 'document-page',
              params: {
                libraryId: mention.library,
                documentId: mention.documentId,
                pageId: mention.pageId,
              },
              query: { selectedPerson: personId },
            }"
            class="group block py-6 outline-none"
          >
            <PersonMentionItem :mention="mention" />
          </RouterLink>
          <PersonMentionItemSkeleton v-if="isLoading" />
        </TabsContent>

        <TabsContent value="discover">
          <PersonDiscoveryPanel
            v-model:search-term="personSearchTerm"
            :faces="similarFaces"
            :people="similarPeople"
            :current-name="profile.name"
            :reference-face-count="faceIds.length"
            :assigning-faces="assignmentStatus === 'pending'"
            :merging-people="mergeStatus === 'pending'"
            :merge-succeeded="mergeStatus === 'success'"
            :merge-failed="mergeStatus === 'error'"
            :loading-faces="isLoadingFaces"
            :loading-people="isLoadingPeople"
            :error="discoveryError"
            @assign-faces="assignFaces"
            @merge-people="mergePeople"
          />
        </TabsContent>
      </Tabs>
    </template>
  </main>
</template>
