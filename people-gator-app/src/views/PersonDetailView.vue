<script setup lang="ts">
import { Image, ScanFace } from '@lucide/vue'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PersonEditableDetails from '@/components/custom/PersonEditableDetails.vue'
import PersonFaceCard from '@/components/custom/PersonFaceCard.vue'
import PersonFaceCardSkeleton from '@/components/custom/PersonFaceCardSkeleton.vue'
import PersonMentionItem from '@/components/custom/PersonMentionItem.vue'
import PersonMentionItemSkeleton from '@/components/custom/PersonMentionItemSkeleton.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { usePersonDetail } from '@/query/person-detail'

const route = useRoute()
const router = useRouter()
const personId = computed(() => String(route.params.personId))

const {
  error,
  faces,
  identifiers,
  isLoading,
  libraryCount,
  mentions,
  portrait,
  profile,
  updateProfile,
} = usePersonDetail(personId)

const activeTab = computed(() => (route.query.tab === 'mentions' ? 'mentions' : 'faces'))

function selectTab(tab: string | number) {
  const selectedTab = tab === 'mentions' ? 'mentions' : 'faces'
  void router.replace({
    name: 'person-detail',
    params: { personId: personId.value },
    query: selectedTab === 'mentions' ? { tab: selectedTab } : {},
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
        :face-count="faces.length"
        :mention-count="mentions.length"
        :library-count="libraryCount"
        :wikidata-id="identifiers.wikidataId"
        :national-library-authority-id="identifiers.nationalLibraryAuthorityId"
        @update:model-value="updateProfile"
      />

      <Tabs :model-value="activeTab" class="mt-8" @update:model-value="selectTab">
        <h2>Evidence across the archive</h2>
        <TabsList aria-label="Person occurrences" class="gap-2 mt-4">
          <TabsTrigger value="faces">
            <ScanFace class="size-4" aria-hidden="true" /> Faces
            <span class="font-mono">{{ faces.length }}</span>
          </TabsTrigger>
          <TabsTrigger value="mentions">
            <Image class="size-4" aria-hidden="true" /> Mentions
            <span class="font-mono">{{ mentions.length }}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent
          value="faces"
          class="grid gap-4 pt-6 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4"
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
            }"
            class="group block py-6 outline-none"
          >
            <PersonMentionItem :mention="mention" />
          </RouterLink>
          <PersonMentionItemSkeleton v-if="isLoading" />
        </TabsContent>
      </Tabs>
    </template>
  </main>
</template>
