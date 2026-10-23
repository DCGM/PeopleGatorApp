<script setup lang="ts">
import SharedFilterControls from '@/components/custom/SharedFilterControls.vue'
import SharedFilterTags from '@/components/custom/SharedFilterTags.vue'
import SearchFilterPanel from '@/components/custom/SearchFilterPanel.vue'
import { useSharedFilters, queryValues } from '@/viewmodels/shared-filters'
import { Image, ScanFace, UserRoundSearch } from '@lucide/vue'
import { useDebounce } from '@vueuse/core'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useLinkStateFilter } from '@/composables/link-state-filter'
import EntityLinkStatistics from '@/components/custom/EntityLinkStatistics.vue'
import { Button } from '@/components/ui/button'
import PersonEditableDetails from '@/components/custom/PersonEditableDetails.vue'
import PersonProcessingDetails from '@/components/custom/PersonProcessingDetails.vue'
import PersonDiscoveryPanel from '@/components/custom/PersonDiscoveryPanel.vue'
import PersonFacesPanel from '@/components/custom/PersonFacesPanel.vue'
import PersonFaceCardSkeleton from '@/components/custom/PersonFaceCardSkeleton.vue'
import PersonMentionEntry from '@/components/custom/PersonMentionEntry.vue'
import PersonMentionGroups from '@/components/custom/PersonMentionGroups.vue'
import SortControl from '@/components/custom/SortControl.vue'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useRouteSort } from '@/lib/sorting'
import {
  DISCOVERY_FACE_SORT_KEYS,
  FACE_DEFAULT,
  FACE_SORT_KEYS,
  FACE_SORTS,
  MENTION_DEFAULT,
  MENTION_GROUP_DEFAULT,
  MENTION_GROUP_SORT_KEYS,
  MENTION_GROUP_SORTS,
  MENTION_SORT_KEYS,
  MENTION_SORTS,
  PEOPLE_SORTS,
  RELEVANCE,
  SIMILAR_PEOPLE_SORT_KEYS,
  scoredOptions,
} from '@/viewmodels/sort-options'
import PersonMentionItemSkeleton from '@/components/custom/PersonMentionItemSkeleton.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { usePersonDiscovery, DISCOVERY_ANNOTATIONS } from '@/viewmodels/person-discovery'
import { useFaceModels } from '@/query/face-models'
import type { EntityAnnotation } from '@/client'
import { usePersonDetail } from '@/viewmodels/person-detail'

const route = useRoute()
const router = useRouter()
const evidence = useSharedFilters()
const matchingFaceIds = computed(() => queryValues(route.query.origin_matched_face))
const linkStates = useLinkStateFilter()
const personId = computed(() => String(route.params.personId))

// Each tab and Discover list keeps an independent, shareable order.
const faceSortOptions = scoredOptions(FACE_SORTS, false)
const faceSort = useRouteSort(FACE_SORT_KEYS, faceSortOptions, FACE_DEFAULT)
const mentionSort = useRouteSort(MENTION_SORT_KEYS, MENTION_SORTS, MENTION_DEFAULT)
const groupSort = useRouteSort(MENTION_GROUP_SORT_KEYS, MENTION_GROUP_SORTS, MENTION_GROUP_DEFAULT)
const similarFaceSort = useRouteSort(DISCOVERY_FACE_SORT_KEYS, FACE_SORTS, RELEVANCE)
const similarPeopleSort = useRouteSort(SIMILAR_PEOPLE_SORT_KEYS, PEOPLE_SORTS, RELEVANCE)
const mentionView = computed<'flat' | 'groups'>({
  get: () => (route.query.mention_view === 'groups' ? 'groups' : 'flat'),
  set: (value) =>
    void router.push({
      query: { ...route.query, mention_view: value === 'groups' ? 'groups' : undefined },
    }),
})

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
  faceCount,
  faces,
  identifiers,
  libraryCount,
  mentionCount,
  mentionFilters,
  mentions,
  portraitFaceId,
  profile,
  processing,
  updateIdentifiers,
  updateProfile,
} = usePersonDetail(
  personId,
  linkStates,
  evidence.params,
  computed(() => !evidence.error.value),
  matchingFaceIds,
  faceSort,
  mentionSort,
  computed(() => mentionView.value === 'flat'),
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
const faceModels = useFaceModels(computed(() => activeTab.value === 'discover'))
const modelOptions = computed(() =>
  (faceModels.data.value?.items ?? []).map((model) => ({
    value: model.model_stub,
    label: model.model_stub,
  })),
)
const defaultDiscoveryModel = computed(
  () =>
    modelOptions.value.find((model) => model.value === 'vit_small_patch8_gap_112.cosface_ms1mv3')
      ?.value ??
    modelOptions.value[0]?.value ??
    '',
)
const discoveryModel = computed({
  get: () =>
    typeof route.query.discovery_model === 'string'
      ? route.query.discovery_model
      : defaultDiscoveryModel.value,
  set: (value: string) =>
    void router.replace({ query: { ...route.query, discovery_model: value || undefined } }),
})
const discoveryAnnotations = computed<EntityAnnotation[]>({
  get: () =>
    route.query.discovery_annotations === undefined
      ? [...DISCOVERY_ANNOTATIONS]
      : DISCOVERY_ANNOTATIONS.filter((item) =>
          queryValues(route.query.discovery_annotations).includes(item),
        ),
  set: (value) =>
    void router.replace({
      query: {
        ...route.query,
        discovery_annotations: value.length === 3 ? undefined : value.length ? value : 'none',
      },
    }),
})

watch(
  () => route.query.discovery_text,
  (text) => {
    personSearchTerm.value = typeof text === 'string' ? text : ''
  },
)

watch(personSearchTerm, (text) => {
  if (activeTab.value === 'discover')
    void router.replace({ query: { ...route.query, discovery_text: text || undefined } })
})

const {
  assignFaces,
  assignmentStatus,
  searchError: discoveryError,
  retry: retryDiscovery,
  isLoadingFaces,
  isLoadingPeople,
  mergePeople,
  mergeStatus,
  similarFaces,
  similarPeople,
} = usePersonDiscovery(
  personId,
  discoveryModel,
  debouncedPersonSearchTerm,
  computed(() => activeTab.value === 'discover'),
  similarFaceSort,
  similarPeopleSort,
  discoveryAnnotations,
)

function selectTab(tab: string | number) {
  const selectedTab = tab === 'mentions' || tab === 'discover' ? tab : 'faces'
  void router.replace({
    name: 'person-detail',
    params: { personId: personId.value },
    query: { ...route.query, tab: selectedTab === 'faces' ? undefined : selectedTab },
  })
}

function clearDiscoveryFilters() {
  void router.replace({
    query: { ...route.query, discovery_model: undefined, discovery_annotations: undefined },
  })
}

function retrySearch() {
  retryDiscovery()
  void faceModels.refetch()
}
</script>

<template>
  <main class="mx-auto w-full max-w-6xl px-4 pb-12 pt-7 sm:px-6">
    <p v-if="error" class="py-16 text-center text-destructive">Could not load this person.</p>
    <template v-else>
      <PersonEditableDetails
        :model-value="profile"
        :person-id="personId"
        :thumbnail-face-id="portraitFaceId"
        :face-count="entity?.entity_link_stats?.faces?.total ?? faceCount"
        :mention-count="entity?.entity_link_stats?.mentions?.total ?? mentionCount"
        :library-count="libraryCount"
        :wikidata-id="identifiers.wikidataId"
        :national-library-authority-id="identifiers.nationalLibraryAuthorityId"
        @update:model-value="updateProfile"
        @update:identifiers="updateIdentifiers"
      >
        <template #statistics>
          <EntityLinkStatistics :stats="entity?.entity_link_stats" layout="person" />
          <PersonProcessingDetails v-if="entity" :key="personId" :processing="processing" />
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
            ><SharedFilterControls
          /></SearchFilterPanel>
          <SharedFilterTags />
          <p v-if="missingMatchedFaces" role="status">
            A matching face is unavailable or outside the current filters.
          </p>
        </div>

        <TabsContent
          value="faces"
          class="grid grid-cols-2 gap-3 pt-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6"
        >
          <div class="col-span-full flex flex-wrap gap-2">
            <SortControl v-model="faceSort" :options="faceSortOptions" label="Sort faces" />
          </div>
          <PersonFacesPanel
            :key="personId"
            :faces="faces"
            :person-name="profile.name"
            :person-id="personId"
            :thumbnail-face-id="entity?.thumbnail_face_id"
            :thumbnail-mode="entity?.thumbnail_mode"
          />
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
              No faces match the filters.
              <Button variant="link" @click="evidence.clear()">Clear filters</Button>
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

        <TabsContent value="mentions">
          <div class="flex flex-wrap items-center gap-2 pt-6">
            <ToggleGroup
              type="single"
              variant="outline"
              :model-value="mentionView"
              aria-label="Mention view"
              @update:model-value="(value) => value && (mentionView = value as 'flat' | 'groups')"
            >
              <ToggleGroupItem value="flat">Flat</ToggleGroupItem>
              <ToggleGroupItem value="groups">Exact appearance</ToggleGroupItem>
            </ToggleGroup>
            <SortControl
              v-if="mentionView === 'groups'"
              v-model="groupSort"
              :options="MENTION_GROUP_SORTS"
              label="Sort groups"
            />
            <SortControl
              v-model="mentionSort"
              :options="MENTION_SORTS"
              :label="mentionView === 'groups' ? 'Sort occurrences' : 'Sort mentions'"
            />
          </div>
          <PersonMentionGroups
            v-if="mentionView === 'groups'"
            :filters="mentionFilters"
            :group-sort="groupSort"
            :occurrence-sort="mentionSort"
            :person-id="personId"
            :link-states="linkStates"
            :enabled="!evidence.error.value"
            @broaden="evidence.clear()"
          />
          <div v-else class="divide-y">
            <PersonMentionEntry
              v-for="mention in mentions"
              :key="mention.id"
              :mention="mention"
              :person-id="personId"
              :link-states="linkStates"
            />
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
                No mentions match the filters.
                <Button variant="link" @click="evidence.clear()">Clear filters</Button>
              </p>
              <Button
                v-if="hasMoreMentions"
                variant="outline"
                :disabled="loadingMoreMentions"
                @click="loadMoreMentions()"
                >Load more mentions</Button
              >
            </div>
          </div>
        </TabsContent>

        <TabsContent value="discover">
          <PersonDiscoveryPanel
            v-model:search-term="personSearchTerm"
            v-model:annotations="discoveryAnnotations"
            v-model:face-model="discoveryModel"
            :model-options="modelOptions"
            :default-face-model="defaultDiscoveryModel"
            v-model:face-sort="similarFaceSort"
            v-model:people-sort="similarPeopleSort"
            :face-sort-options="FACE_SORTS"
            :people-sort-options="PEOPLE_SORTS"
            :faces="similarFaces"
            :people="similarPeople"
            :current-name="profile.name"
            :reference-face-count="entity?.entity_link_stats?.faces?.total ?? faceCount"
            :assigning-faces="assignmentStatus === 'pending'"
            :assignment-failed="assignmentStatus === 'error'"
            :merging-people="mergeStatus === 'pending'"
            :merge-succeeded="mergeStatus === 'success'"
            :merge-failed="mergeStatus === 'error'"
            :loading-faces="isLoadingFaces"
            :loading-people="isLoadingPeople"
            :search-error="discoveryError ?? faceModels.error.value"
            @clear-filters="clearDiscoveryFilters"
            @retry="retrySearch"
            @assign-faces="assignFaces"
            @merge-people="mergePeople"
          />
        </TabsContent>
      </Tabs>
    </template>
  </main>
</template>
