<script setup lang="ts">
import { Image, ScanFace } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PersonEditableDetails from '@/components/custom/PersonEditableDetails.vue'
import PersonFaceCard from '@/components/custom/PersonFaceCard.vue'
import PersonMentionItem from '@/components/custom/PersonMentionItem.vue'
import type {
  PersonFace,
  PersonMention,
  PersonProfile,
} from '@/components/custom/person-detail.types'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const route = useRoute()
const router = useRouter()
const personId = computed(() => String(route.params.personId))

function nameFromId(id: string) {
  return id
    .split('-')
    .map((part) => part.charAt(0).toLocaleUpperCase('cs') + part.slice(1))
    .join(' ')
}

const profile = ref<PersonProfile>({
  name: personId.value === 'anna-novakova' ? 'Anna Nováková' : nameFromId(personId.value),
  shortDescription: 'Local lecturer, historian, and organizer of the town history programme.',
  article:
    'Anna Nováková was an active figure in the cultural life of the region during the interwar period. She organized public lectures, contributed to local historical societies, and worked to preserve accounts of everyday civic life. Newspaper reports place her at meetings across several Moravian towns, often speaking about education, community archives, and the role of women in public associations.',
  aliases: ['Anna Novák', 'A. Nováková', 'Anna Novakova'],
})

const faces: PersonFace[] = [
  {
    id: 'face-01',
    portrait:
      'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=520&q=85',
    status: 'valid',
    confidence: 96,
    library: 'MZK',
    documentId: 'lidove-noviny-1934',
    pageId: 'page-12',
    pageLabel: 'Page 12',
  },
  {
    id: 'face-04',
    portrait:
      'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=520&q=85',
    status: 'auto',
    confidence: 88,
    library: 'NKP',
    documentId: 'narodni-listy-1936',
    pageId: 'page-07',
    pageLabel: 'Page 7',
  },
  {
    id: 'face-09',
    portrait:
      'https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=520&q=85',
    status: 'change',
    confidence: 74,
    library: 'MZK',
    documentId: 'obcansky-vestnik-1938',
    pageId: 'page-03',
    pageLabel: 'Page 3',
  },
  {
    id: 'face-12',
    portrait:
      'https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=520&q=85',
    status: 'valid',
    confidence: 91,
    library: 'MU',
    documentId: 'spolkovy-zivot-1939',
    pageId: 'page-21',
    pageLabel: 'Page 21',
  },
]

const mentions: PersonMention[] = [
  {
    id: 'mention-01',
    excerpt:
      'Na včerejší schůzi vystoupila paní Anna Nováková, která představila program podzimních přednášek.',
    matchedText: 'Anna Nováková',
    library: 'MZK',
    documentId: 'lidove-noviny-1934',
    documentTitle: 'Lidové noviny',
    pageId: 'page-12',
    pageLabel: '12',
    lineId: 'line-anna',
    date: '14 October 1934',
  },
  {
    id: 'mention-02',
    excerpt: 'Přednášku o městských archivech povede historička A. Nováková v obecním sále.',
    matchedText: 'A. Nováková',
    library: 'NKP',
    documentId: 'narodni-listy-1936',
    documentTitle: 'Národní listy',
    pageId: 'page-07',
    pageLabel: '7',
    lineId: 'line-program',
    date: '3 March 1936',
  },
  {
    id: 'mention-03',
    excerpt:
      'Mezi členy přípravného výboru byla zvolena také Anna Novák, zástupkyně místního historického spolku.',
    matchedText: 'Anna Novák',
    library: 'MU',
    documentId: 'spolkovy-zivot-1939',
    documentTitle: 'Spolkový život',
    pageId: 'page-21',
    pageLabel: '21',
    lineId: 'line-attendees',
    date: '22 September 1939',
  },
]

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
    <PersonEditableDetails v-model="profile" :person-id="personId" :portrait="faces[0]!.portrait"
      :face-count="faces.length" :mention-count="mentions.length" :library-count="3" />

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

      <TabsContent value="faces" class="grid gap-4 pt-6 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        <RouterLink :to="{
          name: 'document-page',
          params: { libraryId: face.library, documentId: face.documentId, pageId: face.pageId },
          query: { person: face.id },
        }" v-for="face in faces" :key="face.id" class="group">
          <PersonFaceCard :face="face" :person-name="profile.name" />
        </RouterLink>
      </TabsContent>

      <TabsContent value="mentions" class="divide-y">
        <RouterLink v-for="mention in mentions" :key="mention.id" :to="{
          name: 'document-page',
          params: {
            libraryId: mention.library,
            documentId: mention.documentId,
            pageId: mention.pageId,
          },
          query: { line: mention.lineId, context: '3' },
        }" class="group block py-6 outline-none">
          <PersonMentionItem :mention="mention" />
        </RouterLink>
      </TabsContent>
    </Tabs>
  </main>
</template>
