<script setup lang="ts">
import SharedFilterControls from '@/components/custom/SharedFilterControls.vue'
import SharedFilterTags from '@/components/custom/SharedFilterTags.vue'
import SearchFilterPanel from '@/components/custom/SearchFilterPanel.vue'
import { useSharedFilters, queryValues } from '@/viewmodels/shared-filters'
import { useDebounce } from '@vueuse/core'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useLinkStateFilter } from '@/composables/link-state-filter'
import EntityLinkStatistics from '@/components/custom/EntityLinkStatistics.vue'
import { Button } from '@/components/ui/button'
import PersonPortrait from '@/components/custom/PersonPortrait.vue'
import PersonEditableDetails from '@/components/custom/PersonEditableDetails.vue'
import PersonLibraryCount from '@/components/custom/PersonLibraryCount.vue'
import PersonProcessingDetails from '@/components/custom/PersonProcessingDetails.vue'
import PersonDiscoveryPanel from '@/components/custom/PersonDiscoveryPanel.vue'
import PersonFacesPanel from '@/components/custom/PersonFacesPanel.vue'
import PersonFaceCardSkeleton from '@/components/custom/PersonFaceCardSkeleton.vue'
import PersonMentionReviewList from '@/components/custom/PersonMentionReviewList.vue'
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
const mentionView = computed<'flat' | 'groups' | 'document' | 'page'>({
  get: () => {
    const mode = route.query.mention_view
    return mode === 'groups' || mode === 'document' || mode === 'page' ? mode : 'flat'
  },
  set: (value) =>
    void router.push({
      query: { ...route.query, mention_view: value === 'flat' ? undefined : value },
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
  if (route.query.tab === 'details') return 'details'
  if (route.query.tab === 'statistics') return 'statistics'
  return 'faces'
})
const personSearchTerm = ref(
  typeof route.query.people_text === 'string'
    ? route.query.people_text
    : typeof route.query.discovery_text === 'string'
      ? route.query.discovery_text
      : '',
)
const debouncedPersonSearchTerm = useDebounce(personSearchTerm, 300)
const faceModels = useFaceModels(computed(() => activeTab.value === 'faces'))
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
    void router.replace({
      query: {
        ...route.query,
        people_model: peopleDiscoveryModel.value || undefined,
        discovery_model: value || undefined,
      },
    }),
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
        people_annotations: serializeAnnotations(peopleDiscoveryAnnotations.value),
        discovery_annotations: value.length === 3 ? undefined : value.length ? value : 'none',
      },
    }),
})

// Old discovery URLs seed both sections. Each selector preserves the other
// section's effective choices before changing its own URL state.
function serializeAnnotations(value: EntityAnnotation[]) {
  return value.length === 3 ? 'all' : value.length ? value : 'none'
}
const peopleDiscoveryModel = computed({
  get: () =>
    typeof route.query.people_model === 'string' ? route.query.people_model : discoveryModel.value,
  set: (value: string) =>
    void router.replace({
      query: { ...route.query, people_model: value || defaultDiscoveryModel.value || undefined },
    }),
})
const peopleDiscoveryAnnotations = computed<EntityAnnotation[]>({
  get: () =>
    route.query.people_annotations === undefined
      ? discoveryAnnotations.value
      : route.query.people_annotations === 'all'
        ? [...DISCOVERY_ANNOTATIONS]
        : DISCOVERY_ANNOTATIONS.filter((item) =>
            queryValues(route.query.people_annotations).includes(item),
          ),
  set: (value) =>
    void router.replace({
      query: { ...route.query, people_annotations: serializeAnnotations(value) },
    }),
})

// Legacy face text remains a removable tag, without restoring a search field.
const legacyFaceText = computed({
  get: () => (typeof route.query.discovery_text === 'string' ? route.query.discovery_text : ''),
  set: (value: string) =>
    void router.replace({
      query: {
        ...route.query,
        people_text: personSearchTerm.value || undefined,
        discovery_text: value || undefined,
      },
    }),
})
watch(
  () => [route.query.people_text, route.query.discovery_text],
  ([peopleText, legacyText]) => {
    personSearchTerm.value =
      typeof peopleText === 'string' ? peopleText : typeof legacyText === 'string' ? legacyText : ''
  },
)
watch(personSearchTerm, (text) => {
  if (activeTab.value === 'faces')
    void router.replace({
      query: { ...route.query, people_text: text || (legacyFaceText.value ? '' : undefined) },
    })
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
  hasMoreFaces: hasMoreFoundFaces,
  loadingMoreFaces: loadingMoreFoundFaces,
  moreFacesFailed,
  foundFaceCount,
  loadMoreFaces: loadMoreFoundFaces,
  similarPeople,
} = usePersonDiscovery(
  personId,
  discoveryModel,
  legacyFaceText,
  computed(() => activeTab.value === 'faces'),
  similarFaceSort,
  similarPeopleSort,
  discoveryAnnotations,
  computed(() => ({
    model: peopleDiscoveryModel.value,
    text: debouncedPersonSearchTerm.value,
    annotations: peopleDiscoveryAnnotations.value,
  })),
  computed(() =>
    route.query.discovery_assignment === 'assigned' ||
    route.query.discovery_assignment === 'unassigned'
      ? route.query.discovery_assignment
      : 'all',
  ),
)

function selectTab(tab: string | number) {
  const selectedTab =
    tab === 'mentions' || tab === 'details' || tab === 'statistics' ? tab : 'faces'
  void router.replace({
    name: 'person-detail',
    params: { personId: personId.value },
    query: { ...route.query, tab: selectedTab === 'faces' ? undefined : selectedTab },
  })
}

function clearDiscoveryFilters() {
  void router.replace({
    query: {
      ...route.query,
      people_model: peopleDiscoveryModel.value || undefined,
      people_annotations: serializeAnnotations(peopleDiscoveryAnnotations.value),
      people_text: personSearchTerm.value || undefined,
      discovery_text: undefined,
      discovery_model: undefined,
      discovery_annotations: undefined,
    },
  })
}

function clearPeopleDiscoveryFilters() {
  void router.replace({
    query: {
      ...route.query,
      people_model: defaultDiscoveryModel.value || undefined,
      people_annotations: 'all',
    },
  })
}

function retrySearch() {
  retryDiscovery()
  void faceModels.refetch()
}
</script>

<template>
  <main class="mx-auto w-full max-w-6xl [&_*]:scroll-mt-40 px-4 pb-12 pt-7 sm:px-6">
    <p v-if="error" class="py-16 text-center text-destructive">Could not load this person.</p>
    <template v-else>
      <header
        class="sticky top-13 z-30 flex min-w-0 items-center gap-3 border-b bg-background py-3"
        aria-label="Person identity"
      >
        <PersonPortrait :name="profile.name" :face-id="portraitFaceId" class="size-12 shrink-0" />
        <div class="min-w-0">
          <h1 class="truncate text-xl" :title="profile.name">{{ profile.name }}</h1>
          <p
            v-if="profile.shortDescription"
            class="line-clamp-2 text-sm text-muted-foreground"
            :title="profile.shortDescription"
          >
            {{ profile.shortDescription }}
          </p>
        </div>
      </header>

      <Tabs :model-value="activeTab" class="mt-4" @update:model-value="selectTab">
        <TabsList aria-label="Person record sections" class="max-w-full flex-wrap h-auto">
          <TabsTrigger value="faces">
            Faces
            <span class="font-mono">{{
              entity?.entity_link_stats?.faces?.total ?? faceCount
            }}</span>
          </TabsTrigger>
          <TabsTrigger value="mentions">
            Mentions
            <span class="font-mono">{{
              entity?.entity_link_stats?.mentions?.total ?? mentionCount
            }}</span>
          </TabsTrigger>
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="statistics">Statistics</TabsTrigger>
        </TabsList>
        <div v-if="activeTab === 'faces' || activeTab === 'mentions'" class="mt-3">
          <SearchFilterPanel label="Person evidence" filters-only
            ><SharedFilterControls
          /></SearchFilterPanel>
          <SharedFilterTags />
          <p v-if="missingMatchedFaces" role="status">
            A matching face is unavailable or outside the current filters.
          </p>
        </div>

        <TabsContent value="faces" class="space-y-3 pt-4">
          <div class="col-span-full flex flex-wrap gap-2">
            <SortControl v-model="faceSort" :options="faceSortOptions" label="Sort faces" />
          </div>
          <PersonFacesPanel
            :key="personId"
            collapsible
            :has-more="hasMoreFaces"
            :matching-count="faceCount"
            :faces="faces"
            :person-name="profile.name"
            :person-id="personId"
            :thumbnail-face-id="entity?.thumbnail_face_id"
            :thumbnail-mode="entity?.thumbnail_mode"
          >
            <template #pagination>
              <Button
                v-if="hasMoreFaces"
                variant="outline"
                :disabled="loadingMoreFaces"
                @click="loadMoreFaces()"
                >Load more faces</Button
              >
            </template>
          </PersonFacesPanel>
          <PersonFaceCardSkeleton v-if="faceLoading" />
          <div v-if="faceError || (!faceLoading && !faces.length)" class="col-span-full text-sm">
            <p v-if="faceError" role="alert">
              Could not load faces. <Button variant="link" @click="retryFaces()">Retry</Button>
            </p>
            <p v-if="!faceError && !faceLoading && !faces.length">
              No faces match the filters.
              <Button variant="link" @click="evidence.clear()">Clear filters</Button>
            </p>
          </div>
          <PersonDiscoveryPanel
            v-model:search-term="personSearchTerm"
            v-model:face-search-term="legacyFaceText"
            v-model:annotations="discoveryAnnotations"
            v-model:people-annotations="peopleDiscoveryAnnotations"
            v-model:people-face-model="peopleDiscoveryModel"
            v-model:face-model="discoveryModel"
            :model-options="modelOptions"
            :default-face-model="defaultDiscoveryModel"
            v-model:face-sort="similarFaceSort"
            v-model:people-sort="similarPeopleSort"
            :face-sort-options="FACE_SORTS"
            :people-sort-options="PEOPLE_SORTS"
            :faces="similarFaces"
            :face-count="foundFaceCount"
            :has-more-faces="hasMoreFoundFaces"
            :loading-more-faces="loadingMoreFoundFaces"
            :more-faces-failed="moreFacesFailed"
            @load-more-faces="loadMoreFoundFaces"
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
            @clear-people-filters="clearPeopleDiscoveryFilters"
            @retry="retrySearch"
            @assign-faces="assignFaces"
            @merge-people="mergePeople"
          />
        </TabsContent>

        <TabsContent value="mentions">
          <div class="flex flex-wrap items-center gap-2 pt-6">
            <ToggleGroup
              type="single"
              variant="outline"
              :model-value="mentionView"
              aria-label="Mention view"
              @update:model-value="
                (value) => value && (mentionView = value as 'flat' | 'groups' | 'document' | 'page')
              "
            >
              <ToggleGroupItem value="flat">Flat</ToggleGroupItem>
              <ToggleGroupItem value="document">Document</ToggleGroupItem>
              <ToggleGroupItem value="page">Page</ToggleGroupItem>
              <ToggleGroupItem value="groups">Mention</ToggleGroupItem>
            </ToggleGroup>
            <SortControl
              v-if="mentionView !== 'flat'"
              v-model="groupSort"
              :options="MENTION_GROUP_SORTS"
              label="Sort groups"
              prefix="Groups"
            />
            <SortControl
              v-model="mentionSort"
              :options="MENTION_SORTS"
              :label="mentionView !== 'flat' ? 'Sort occurrences' : 'Sort mentions'"
              :prefix="mentionView !== 'flat' ? 'Occurrences' : 'Sort'"
            />
          </div>
          <PersonMentionGroups
            v-if="mentionView !== 'flat'"
            :filters="mentionFilters"
            :mode="mentionView === 'groups' ? 'mention' : mentionView"
            :group-sort="groupSort"
            :occurrence-sort="mentionSort"
            :person-id="personId"
            :link-states="linkStates"
            :enabled="!evidence.error.value"
            @broaden="evidence.clear()"
          />
          <div v-else class="divide-y">
            <PersonMentionReviewList
              :mentions="mentions"
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

        <TabsContent value="details">
          <PersonEditableDetails
            hide-statistics
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
          </PersonEditableDetails>
        </TabsContent>
        <TabsContent value="statistics" class="space-y-4 pt-4">
          <PersonLibraryCount :person-id="personId" />
          <EntityLinkStatistics :stats="entity?.entity_link_stats" layout="person" />
          <PersonProcessingDetails v-if="entity" :key="personId" :processing="processing" />
        </TabsContent>
      </Tabs>
    </template>
  </main>
</template>
