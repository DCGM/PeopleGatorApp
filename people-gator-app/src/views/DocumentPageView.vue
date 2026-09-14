<script setup lang="ts">
import Panzoom, { type PanzoomObject } from '@panzoom/panzoom'
import {
  ChevronRight,
  Crosshair,
} from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import DocumentControls from '@/components/custom/DocumentControls.vue'
import DocumentTeleprompter from '@/components/custom/DocumentTeleprompter.vue'
import type {
  Face,
  TranscriptionEntitySpan,
  TranscriptionLine,
  TranscriptionLineId,
  TranslationLanguage,
} from '@/components/custom/document-page.types'
import { Button } from '@/components/ui/button'

const minimumZoomPercent = 55
const maximumZoomPercent = 350

const route = useRoute()
const router = useRouter()

const faces: Face[] = [
  {
    id: 'face-01',
    personId: 'anna-novakova',
    name: 'Anna Nováková',
    confidence: 96,
    position: { left: 16, top: 14, width: 21, height: 19 },
    portrait: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=240&q=85',
  },
  {
    id: 'face-02',
    personId: 'josef-svoboda',
    name: 'Josef Svoboda',
    confidence: 88,
    position: { left: 63, top: 50, width: 17, height: 15 },
    portrait: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=240&q=85',
  },
  {
    id: 'face-03',
    personId: null,
    name: 'Unknown person',
    confidence: 64,
    position: { left: 41, top: 70, width: 15, height: 13 },
    portrait: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=240&q=85',
  },
]

const transcription: TranscriptionLine[] = [
  {
    id: 'line-intro',
    text: 'Spolkový život v našem městě vstupuje do nové sezóny.',
    position: { left: 6, top: 40, width: 27, height: 2.3 },
  },
  {
    id: 'line-anna',
    text: 'Na včerejší schůzi vystoupila paní Anna Nováková,',
    position: { left: 36, top: 27, width: 29, height: 2.3 },
    entities: [{ label: 'person', text: 'Anna Nováková', line_id: 'line-anna', start_index: 35, end_index: 48 }],
  },
  {
    id: 'line-program',
    text: 'která představila program podzimních přednášek zaměřených na historii města, místní spolky a významné osobnosti veřejného života.',
    position: { left: 36, top: 29.6, width: 29, height: 2.3 },
  },
  {
    id: 'line-attendees',
    text: 'Setkání se zúčastnili také zástupci okolních obcí.',
    position: { left: 36, top: 32.2, width: 29, height: 2.3 },
  },
  {
    id: 'line-next-meeting',
    text: 'Další veřejná schůze proběhne v pátek 18. října.',
    position: { left: 68, top: 27, width: 26, height: 2.3 },
    entities: [{ label: 'date', text: '18. října', line_id: 'line-next-meeting', start_index: 38, end_index: 47 }],
  },
  {
    id: 'line-details',
    text: 'Podrobný pořad bude zveřejněn v příštím vydání.',
    position: { left: 68, top: 29.6, width: 26, height: 2.3 },
  },
]

const translations = {
  en: {
    'line-intro': 'Community life in our town is entering a new season.',
    'line-anna': 'At yesterday’s meeting, Mrs Anna Nováková spoke,',
    'line-program': 'presenting a programme of autumn lectures focused on the town’s history, local associations, and prominent figures in public life.',
    'line-attendees': 'Representatives of the surrounding municipalities also attended the meeting.',
    'line-next-meeting': 'The next public meeting will take place on Friday, 18 October.',
    'line-details': 'The detailed programme will be published in the next issue.',
  },
  de: {
    'line-intro': 'Das Vereinsleben in unserer Stadt beginnt eine neue Saison.',
    'line-anna': 'Bei der gestrigen Sitzung sprach Frau Anna Nováková,',
    'line-program': 'die ein Programm mit Herbstvorträgen zur Stadtgeschichte, zu örtlichen Vereinen und bedeutenden Persönlichkeiten des öffentlichen Lebens vorstellte.',
    'line-attendees': 'An dem Treffen nahmen auch Vertreter der umliegenden Gemeinden teil.',
    'line-next-meeting': 'Die nächste öffentliche Sitzung findet am Freitag, dem 18. Oktober, statt.',
    'line-details': 'Das ausführliche Programm wird in der nächsten Ausgabe veröffentlicht.',
  },
  cs: {
    'line-intro': 'Spolkový život v našem městě vstupuje do nové sezóny.',
    'line-anna': 'Na včerejší schůzi vystoupila paní Anna Nováková,',
    'line-program': 'která představila program podzimních přednášek zaměřených na historii města, místní spolky a významné osobnosti veřejného života.',
    'line-attendees': 'Setkání se zúčastnili také zástupci okolních obcí.',
    'line-next-meeting': 'Další veřejná schůze proběhne v pátek 18. října.',
    'line-details': 'Podrobný pořad bude zveřejněn v příštím vydání.',
  },
} satisfies Record<TranslationLanguage, Record<TranscriptionLineId, string>>

const similarPeople = [
  { id: 'anna-novakova', name: 'Anna Novák', score: 94, portrait: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=160&q=80' },
  { id: 'marie-dvorakova', name: 'Marie Dvořáková', score: 81, portrait: 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=160&q=80' },
  { id: 'alena-horakova', name: 'Alena Horáková', score: 73, portrait: 'https://images.unsplash.com/photo-1531123897727-8f129e1688ce?auto=format&fit=crop&w=160&q=80' },
]

function routeNumber(value: unknown, fallback: number, maximum: number) {
  const parsed = typeof value === 'string' ? Number(value) : Number.NaN
  return Number.isFinite(parsed) ? Math.min(maximum, Math.max(0, parsed)) : fallback
}

function routeLineIndex(value: unknown) {
  if (typeof value !== 'string') return 1
  const idIndex = transcription.findIndex((line) => line.id === value)
  return idIndex >= 0 ? idIndex : routeNumber(value, 1, transcription.length - 1)
}

function routeContextLineCount(value: unknown) {
  return Math.max(1, routeNumber(value, 5, transcription.length - 1))
}

const selectedFaceId = ref(typeof route.query.person === 'string' ? route.query.person : faces[0]!.id)
const selectedLineIndex = ref(routeLineIndex(route.query.line))
const isTranslationOpen = ref(route.query.translate === 'on')
const selectedLanguage = ref<TranslationLanguage>('en')
const contextLineCount = ref(routeContextLineCount(route.query.context))
const zoomPercent = ref(82)
const selectedEntityKey = ref<string | null>(null)
const viewerElement = ref<HTMLElement | null>(null)
const pageElement = ref<HTMLElement | null>(null)
let panzoom: PanzoomObject | undefined

const selectedFace = computed(() => faces.find((face) => face.id === selectedFaceId.value) ?? faces[0]!)
const selectedFaceIndex = computed(() => faces.findIndex((face) => face.id === selectedFace.value.id))
const translationOptions = computed<readonly ('off' | TranslationLanguage)[]>(() => ['off', 'cs', 'en', 'de'])
const currentTranslation = computed(() => {
  const line = transcription[selectedLineIndex.value]!
  return translations[selectedLanguage.value][line.id]
})
const visibleTranscription = computed(() => {
  const visibleCount = Math.min(contextLineCount.value, transcription.length)
  const maximumStart = transcription.length - visibleCount
  const contextBefore = Math.floor(visibleCount / 2)
  const start = Math.min(maximumStart, Math.max(0, selectedLineIndex.value - contextBefore))
  return transcription.slice(start, start + visibleCount).map((line, offset) => ({ index: start + offset, line }))
})

function syncRoute() {
  void router.replace({
    query: {
      ...route.query,
      person: selectedFaceId.value,
      line: transcription[selectedLineIndex.value]!.id,
      translate: isTranslationOpen.value ? 'on' : 'off',
      context: String(contextLineCount.value),
    },
  })
}

function selectTranslation(language: TranslationLanguage | 'off') {
  isTranslationOpen.value = language !== 'off'
  if (language !== 'off') selectedLanguage.value = language
  syncRoute()
}

function selectFace(faceId: string) {
  selectedFaceId.value = faceId
  syncRoute()
}

function selectLine(index: number) {
  if (index < 0 || index >= transcription.length) return
  selectedLineIndex.value = index
  selectedEntityKey.value = null
  syncRoute()
}

function selectEntity(index: number, entity: TranscriptionEntitySpan) {
  selectedLineIndex.value = index
  selectedEntityKey.value = `${entity.line_id}:${entity.start_index}:${entity.end_index}`
  syncRoute()
}

function nextFace() {
  if (selectedFaceIndex.value >= faces.length - 1) return
  selectFace(faces[selectedFaceIndex.value + 1]!.id)
}

function previousFace() {
  if (selectedFaceIndex.value <= 0) return
  selectFace(faces[selectedFaceIndex.value - 1]!.id)
}

function changeContext(direction: 'decrease' | 'increase') {
  const nextCount = contextLineCount.value + (direction === 'increase' ? 1 : -1)
  contextLineCount.value = Math.min(transcription.length % 2 === 0 ? transcription.length - 1 : transcription.length, Math.max(1, nextCount))
  syncRoute()
}

function nextLine() {
  selectLine(Math.min(selectedLineIndex.value + 1, transcription.length - 1))
}

function previousLine() {
  selectLine(Math.max(selectedLineIndex.value - 1, 0))
}

function navigateLine(direction: 'next' | 'previous') {
  if (direction === 'next') nextLine()
  else previousLine()
}

function openPerson(personId: string | null) {
  if (!personId) return
  void router.push({ name: 'person-detail', params: { personId } })
}

function setZoom(direction: 'in' | 'out') {
  if (!panzoom) return
  if (direction === 'in' && zoomPercent.value >= maximumZoomPercent) return
  if (direction === 'out' && zoomPercent.value <= minimumZoomPercent) return
  if (direction === 'in') panzoom.zoomIn()
  else panzoom.zoomOut()
}

function resetView() {
  panzoom?.reset({ animate: true })
}

function handleWheel(event: WheelEvent) {
  if (!panzoom) return
  const page = pageElement.value
  const viewport = viewerElement.value
  if (!page || !viewport) return

  event.preventDefault()
  const viewportBounds = viewport.getBoundingClientRect()
  const focalEvent = new WheelEvent('wheel', {
    clientX: event.clientX + page.offsetWidth / 2 - viewportBounds.width / 2,
    clientY: event.clientY + page.offsetHeight / 2 - viewportBounds.height / 2,
    deltaX: event.deltaX,
    deltaY: event.deltaY,
    deltaMode: event.deltaMode,
  })
  panzoom.zoomWithWheel(focalEvent)
}

function handleNavigationKeydown(event: KeyboardEvent) {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
  if (event.target instanceof HTMLElement && (event.target.isContentEditable || ['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName))) return

  const navigate = {
    ArrowUp: previousLine,
    ArrowDown: nextLine,
    ArrowLeft: previousFace,
    ArrowRight: nextFace,
  }[event.key]

  if (!navigate) return
  event.preventDefault()
  navigate()
}

watch(
  () => route.query.translate,
  (translate) => {
    isTranslationOpen.value = translate === 'on'
  },
)

watch(
  () => route.query.context,
  (context) => {
    contextLineCount.value = routeContextLineCount(context)
  },
)

onMounted(async () => {
  window.addEventListener('keydown', handleNavigationKeydown)
  await nextTick()
  if (!pageElement.value) return
  panzoom = Panzoom(pageElement.value, {
    canvas: true,
    maxScale: maximumZoomPercent / 100,
    minScale: minimumZoomPercent / 100,
    startScale: 0.82,
    step: 0.18,
  })
  viewerElement.value?.addEventListener('wheel', handleWheel, { passive: false })
  pageElement.value.addEventListener('panzoomchange', ((event: CustomEvent<{ scale: number }>) => {
    zoomPercent.value = Math.round(event.detail.scale * 100)
  }) as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleNavigationKeydown)
  viewerElement.value?.removeEventListener('wheel', handleWheel)
  panzoom?.destroy()
})
</script>

<template>
  <main class="workspace-grid">
    <div
      class="mx-auto mb-auto max-h-full w-full max-w-5xl border z-10 bg-background/95 shadow-lg backdrop-blur-sm grid row-start-1 row-span-1 col-start-1 col-span-1">
      <DocumentControls :selected-line-index="selectedLineIndex" :line-count="transcription.length"
        :selected-face-index="selectedFaceIndex" :face-count="faces.length" :zoom-percent="zoomPercent"
        :minimum-zoom-percent="minimumZoomPercent" :maximum-zoom-percent="maximumZoomPercent"
        :translation-options="translationOptions" :is-translation-open="isTranslationOpen"
        :selected-language="selectedLanguage" :context-line-count="contextLineCount"
        :maximum-context-line-count="transcription.length - 1" @previous-line="previousLine" @next-line="nextLine"
        @previous-face="previousFace" @next-face="nextFace" @set-zoom="setZoom" @reset-view="resetView"
        @select-translation="selectTranslation" @change-context="changeContext" />

      <DocumentTeleprompter :visible-transcription="visibleTranscription" :selected-line-index="selectedLineIndex"
        :context-line-count="contextLineCount" :selected-entity-key="selectedEntityKey"
        :is-translation-open="isTranslationOpen" :selected-language="selectedLanguage"
        :current-translation="currentTranslation" @select-line="selectLine" @select-entity="selectEntity"
        @navigate-line="navigateLine" />
    </div>

    <section ref="viewerElement"
      class="bg-viewer overflow-hidden lg:h-auto lg:min-h-0 lg:flex-1 row-start-1 row-span-1 col-start-1 col-span-1"
      aria-label="Pan and zoom document page">

      <div class="panzoom-layer min-h-full min-w-full inset-0 flex items-center justify-center">
        <div ref="pageElement" class="scan-page h-190 w-135 shrink-0 overflow-hidden bg-card shadow-2xl">
          <div class="absolute inset-0 opacity-35 mix-blend-multiply scan-texture" />
          <div class="relative border-b-2 border-foreground/60 px-10 pb-4 pt-8 text-center text-foreground">
            <p class="font-heading text-4xl font-semibold">LIDOVÉ NOVINY</p>
            <p class="mt-1 font-mono text-[9px] uppercase">Ročník XII. · číslo 284 · cena 40 haléřů</p>
          </div>

          <div class="relative grid grid-cols-3 gap-4 px-8 py-5 text-foreground/80">
            <article class="space-y-2 text-[8px] leading-[1.45]">
              <h2 class="text-center text-base leading-none">Ze života našeho města</h2>
              <img :src="faces[0]!.portrait" alt="Portrait printed in the newspaper"
                class="h-32 w-full grayscale object-cover contrast-75" />
              <p v-for="index in 8" :key="`left-${index}`">Spolkový život v našem městě vstupuje do nové sezóny.
                Veřejnost přijala zprávu s velikým zájmem.</p>
            </article>
            <article class="space-y-2 text-[8px] leading-[1.45]">
              <p v-for="index in 14" :key="`middle-${index}`">Na včerejší schůzi byl představen program podzimních
                přednášek. Přítomní zástupci okolních obcí projednali další postup.</p>
            </article>
            <article class="space-y-2 text-[8px] leading-[1.45]">
              <h2 class="border-b border-border pb-1 text-center text-base leading-none">Zprávy dne</h2>
              <p v-for="index in 5" :key="`right-a-${index}`">Další veřejná schůze proběhne v pátek večer. Podrobný
                pořad přineseme příště.</p>
              <img :src="faces[1]!.portrait" alt="Second portrait printed in the newspaper"
                class="h-28 w-full grayscale object-cover contrast-75" />
              <p v-for="index in 5" :key="`right-b-${index}`">Redakce přijímá oznámení každý všední den. Dopisy račte
                zasílati na adresu listu.</p>
            </article>
          </div>

          <button v-for="(line, index) in transcription" :key="line.id" type="button"
            class="absolute border-2 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            :class="index === selectedLineIndex
              ? 'border-accent bg-accent/20 ring-1 ring-background/75'
              : 'border-transparent hover:border-accent/70 hover:bg-accent/10'"
            :style="{ left: `${line.position.left}%`, top: `${line.position.top}%`, width: `${line.position.width}%`, height: `${line.position.height}%` }"
            :aria-label="`Select line ${index + 1}: ${line.text}`" :aria-pressed="index === selectedLineIndex"
            @click.stop="selectLine(index)" />

          <button v-for="face in faces" :key="face.id" type="button" class="absolute border-2 transition-colors" :class="face.id === selectedFace.id
            ? 'border-secondary bg-secondary/15 ring-2 ring-background/80'
            : 'border-accent bg-accent/10 hover:bg-accent/25'"
            :style="{ left: `${face.position.left}%`, top: `${face.position.top}%`, width: `${face.position.width}%`, height: `${face.position.height}%` }"
            :aria-label="`Select ${face.name}`" @click.stop="selectFace(face.id)">
            <span class="absolute -left-0.5 -top-5 bg-foreground px-1.5 py-0.5 font-mono text-[8px] text-background">
              {{ face.id }}
            </span>
          </button>

        </div>
      </div>
    </section>


    <aside class="border-l bg-background row-start-1 row-span-2" aria-labelledby="selected-person-title">
      <div class="sticky top-13">
        <header class="border-b p-5">
          <p class="font-mono text-[10px] uppercase text-secondary">Current selection</p>
          <h2 id="selected-person-title" class="mt-1 text-lg">Selected face</h2>
        </header>

        <div class="p-5">
          <div class="flex items-center gap-4">
            <div class="relative shrink-0">
              <img :src="selectedFace.portrait" :alt="selectedFace.name" class="size-24 object-cover grayscale" />
              <Crosshair class="absolute -bottom-2 -right-2 size-7 border bg-secondary p-1 text-secondary-foreground" />
            </div>
            <div class="min-w-0">
              <h3 class="truncate text-lg">{{ selectedFace.name }}</h3>
              <p class="mt-1 font-mono text-[10px] text-muted-foreground">{{ selectedFace.id }}</p>
              <p class="mt-2 text-xs"><strong>{{ selectedFace.confidence }}%</strong> match confidence</p>
            </div>
          </div>

          <Button class="mt-5 w-full rounded-none" variant="outline" :disabled="!selectedFace.personId"
            @click="openPerson(selectedFace.personId)">
            Open person record
            <ChevronRight />
          </Button>
        </div>

        <section class="border-t p-5" aria-labelledby="similar-title">
          <div class="flex items-end justify-between">
            <h2 id="similar-title" class="text-lg">Similar people</h2>
            <span class="font-mono text-[10px] text-muted-foreground">by face</span>
          </div>
          <div class="mt-3 divide-y border-y">
            <button v-for="person in similarPeople" :key="person.name" type="button"
              class="flex w-full items-center gap-3 py-3 text-left hover:text-accent" @click="openPerson(person.id)">
              <img :src="person.portrait" :alt="person.name" class="size-11 object-cover grayscale" />
              <span class="min-w-0 flex-1">
                <strong class="block truncate text-sm font-medium">{{ person.name }}</strong>
                <span class="text-xs text-muted-foreground">Possible identity</span>
              </span>
              <span class="font-mono text-xs">{{ person.score }}%</span>
            </button>
          </div>
        </section>
      </div>
    </aside>

    <section class="border-t bg-background px-4 py-4 sm:px-6" aria-labelledby="page-faces-title">
      <div class="mb-3 flex items-center justify-between">
        <h2 id="page-faces-title" class="text-base">Faces on this page</h2>
        <span class="font-mono text-[10px] uppercase text-muted-foreground">{{ faces.length }} detections</span>
      </div>
      <div class="flex gap-2 overflow-x-auto pb-1">
        <button v-for="face in faces" :key="face.id" type="button"
          class="flex min-w-48 items-center gap-3 border p-2 text-left transition-colors"
          :class="face.id === selectedFace.id ? 'border-secondary bg-secondary/10' : 'bg-card hover:border-accent'"
          @click="selectFace(face.id)">
          <img :src="face.portrait" :alt="face.name" class="size-14 shrink-0 object-cover grayscale" />
          <span class="min-w-0">
            <strong class="block truncate text-sm font-medium">{{ face.name }}</strong>
            <span class="font-mono text-[10px] text-muted-foreground">{{ face.id }} · {{ face.confidence }}%</span>
          </span>
        </button>
      </div>
    </section>


  </main>
</template>

<style scoped>
.workspace-grid {
  min-height: calc(100vh - 3.25rem);
  min-width: calc(100vw - 30rem);
}

.bg-viewer {
  background-color: var(--color-muted);
  background-image:
    linear-gradient(color-mix(in srgb, var(--color-foreground) 5.5%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--color-foreground) 5.5%, transparent) 1px, transparent 1px);
  background-size: 24px 24px;
}

.scan-page {
  user-select: none;
}

.scan-texture {
  background-image:
    repeating-linear-gradient(0deg, transparent 0 3px, color-mix(in srgb, var(--color-foreground) 8%, transparent) 4px),
    radial-gradient(circle at 18% 24%, color-mix(in srgb, var(--color-secondary) 18%, transparent) 0 1px, transparent 2px);
  background-size: auto, 17px 19px;
}

@media (min-width: 1024px) {
  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 30rem;
    grid-template-rows: minmax(0, 1fr);
  }
}
</style>
