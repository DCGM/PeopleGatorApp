<script setup lang="ts">
import EvidenceFilterControls from '@/components/custom/EvidenceFilterControls.vue'
import EvidenceFilterTags from '@/components/custom/EvidenceFilterTags.vue'
import SearchFilterPanel from '@/components/custom/SearchFilterPanel.vue'
import CreationDetails from '@/components/custom/CreationDetails.vue'
import {
  useEvidenceFilters,
  relatedEvidenceQuery,
  queryValues,
} from '@/viewmodels/evidence-filters'
import { Image, ScanFace, UserRoundSearch } from '@lucide/vue'
import { useDebounce } from '@vueuse/core'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useLinkStateFilter } from '@/composables/link-state-filter'
import EntityLinkStatistics from '@/components/custom/EntityLinkStatistics.vue'
import VerifyEntityLink from '@/components/custom/VerifyEntityLink.vue'
import { Button } from '@/components/ui/button'
import PersonEditableDetails from '@/components/custom/PersonEditableDetails.vue'
import PersonProcessingDetails from '@/components/custom/PersonProcessingDetails.vue'
import PersonDiscoveryPanel from '@/components/custom/PersonDiscoveryPanel.vue'
import PersonFacesPanel from '@/components/custom/PersonFacesPanel.vue'
import PersonFaceCardSkeleton from '@/components/custom/PersonFaceCardSkeleton.vue'
import PersonMentionItem from '@/components/custom/PersonMentionItem.vue'
import PersonMentionItemSkeleton from '@/components/custom/PersonMentionItemSkeleton.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { usePersonDiscovery } from '@/viewmodels/person-discovery'
import { usePersonDetail } from '@/viewmodels/person-detail'

const route = useRoute()
const router = useRouter()
const evidence = useEvidenceFilters()
const matchingFaceIds = computed(() => queryValues(route.query.origin_matched_face))
const linkStates = useLinkStateFilter()
const personId = computed(() => String(route.params.personId))

const {
  entity,
  missingMatchedFaces,
  faceError,
  mentionError,
  faceLoading,
  mentionLoading,
  retryFaces,
  retryMentions,
  hasMoreFaces,
  hasMoreMentions,
  loadingMoreFaces,
  loadingMoreMentions,
  loadMoreFaces,
  loadMoreMentions,
  error,
  faceEmbeddingModel,
  faceCount,
  faceIds,
  faces,
  identifiers,
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
} = usePersonDetail(
  personId,
  linkStates,
  evidence.params,
  computed(() => !evidence.error.value),
  matchingFaceIds,
)

const activeTab = computed(() => {
  if (route.query.tab === 'mentions') return 'mentions'
  if (route.query.tab === 'discover') return 'discover'
  return 'faces'
})
const personSearchTerm = ref(
  typeof route.query.discovery_text === 'string' ? route.query.discovery_text : '',
)
const debouncedPersonSearchTerm = useDebounce(personSearchTerm, 300)
let searchSeeded = typeof route.query.discovery_text === 'string'
let lastSeededName = ''

watch(personId, () => {
  if (typeof route.query.discovery_text === 'string') {
    personSearchTerm.value = route.query.discovery_text
    searchSeeded = true
    lastSeededName = ''
    return
  }
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

watch(
  () => route.query.discovery_text,
  (text) => {
    if (typeof text === 'string') personSearchTerm.value = text
  },
)

watch(personSearchTerm, (text) => {
  if (activeTab.value === 'discover')
    void router.replace({ query: { ...route.query, discovery_text: text || undefined } })
})

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
  computed(() => activeTab.value === 'discover' && !evidence.error.value),
  evidence.params,
)

function selectTab(tab: string | number) {
  const selectedTab = tab === 'mentions' || tab === 'discover' ? tab : 'faces'
  void router.replace({
    name: 'person-detail',
    params: { personId: personId.value },
    query: { ...route.query, tab: selectedTab === 'faces' ? undefined : selectedTab },
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
        :face-count="entity?.entity_link_stats?.faces?.total ?? faceCount"
        :mention-count="entity?.entity_link_stats?.mentions?.total ?? mentionCount"
        :library-count="libraryCount"
        :wikidata-id="identifiers.wikidataId"
        :national-library-authority-id="identifiers.nationalLibraryAuthorityId"
        @update:model-value="updateProfile"
        @update:identifiers="updateIdentifiers"
      >
        <template #statistics>
          <EntityLinkStatistics :stats="entity?.entity_link_stats" />
          <CreationDetails
            v-if="entity"
            :key="personId"
            :record="entity"
            label="Identity creation / import"
            expanded
          />
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
        <div class="mt-3">
          <SearchFilterPanel label="Person evidence" filters-only
            ><EvidenceFilterControls
          /></SearchFilterPanel>
          <EvidenceFilterTags />
          <p v-if="missingMatchedFaces" role="status">
            A matching face is unavailable or outside the current evidence filters. Broaden evidence
            or return to the originating search.
          </p>
        </div>

        <TabsContent
          value="faces"
          class="grid grid-cols-2 gap-3 pt-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6"
        >
          <PersonFacesPanel :key="personId" :faces="faces" :person-name="profile.name" />
          <PersonFaceCardSkeleton v-if="faceLoading" />
          <div class="col-span-full text-sm">
            <p v-if="faceError" role="alert">
              Could not load faces. <Button variant="link" @click="retryFaces()">Retry</Button>
            </p>
            <p v-else-if="!faceLoading">
              Showing {{ faceCount }} of
              {{ entity?.entity_link_stats?.faces?.total ?? faceCount }} faces
            </p>
            <p v-if="!faceError && !faceLoading && !faces.length">
              No faces match the evidence filters.
              <Button variant="link" @click="evidence.clear()">Broaden evidence</Button>
            </p>
            <Button
              v-if="hasMoreFaces"
              variant="outline"
              :disabled="loadingMoreFaces"
              @click="loadMoreFaces()"
              >Load more faces</Button
            >
          </div>
        </TabsContent>

        <TabsContent value="mentions" class="divide-y">
          <div v-for="mention in mentions" :key="mention.id">
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
          <PersonMentionItemSkeleton v-if="mentionLoading" />
          <div class="py-3 text-sm">
            <p v-if="mentionError" role="alert">
              Could not load mentions.
              <Button variant="link" @click="retryMentions()">Retry</Button>
            </p>
            <p v-else-if="!mentionLoading">
              Showing {{ mentionCount }} of
              {{ entity?.entity_link_stats?.mentions?.total ?? mentionCount }} mentions
            </p>
            <p v-if="!mentionError && !mentionLoading && !mentions.length">
              No mentions match the evidence filters.
              <Button variant="link" @click="evidence.clear()">Broaden evidence</Button>
            </p>
            <Button
              v-if="hasMoreMentions"
              variant="outline"
              :disabled="loadingMoreMentions"
              @click="loadMoreMentions()"
              >Load more mentions</Button
            >
          </div>
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
