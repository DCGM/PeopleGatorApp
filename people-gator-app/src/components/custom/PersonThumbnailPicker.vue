<script setup lang="ts">
import { computed, ref, watch, useId } from 'vue'
import PersonPortrait from './PersonPortrait.vue'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useFaceListQuery } from '@/query/faces'
import { usePatchEntityMutation } from '@/query/entities'

const titleId = useId()
const descriptionId = useId()

const props = defineProps<{
  personId: string
  name: string
  selectedFaceId?: string | null
  mode?: 'automatic' | 'manual'
}>()
const open = ref(false)
const selection = usePatchEntityMutation()
// Portrait choices always use the full linked set, independent of evidence filters.
const query = useFaceListQuery(() => ({ 'filter.entity_id': [props.personId], limit: 24 }), open)
const faces = computed(() => (query.data.value?.pages ?? []).flatMap((page) => page.items))
watch(
  () => props.personId,
  () => {
    open.value = false
    selection.reset()
  },
)
watch(open, (isOpen) => {
  if (isOpen && !selection.isPending.value) selection.reset()
})
async function save(faceId: string | null) {
  const personId = props.personId
  try {
    await selection.mutateAsync({ entityId: personId, body: { thumbnail_face_id: faceId } })
    if (props.personId === personId) open.value = false
  } catch {
    // Preserve the server-confirmed portrait and keep the choices available to retry.
  }
}
</script>

<template>
  <Popover v-model:open="open" modal>
    <PopoverTrigger as-child
      ><Button variant="outline" size="sm">Change portrait</Button></PopoverTrigger
    >
    <PopoverContent
      align="start"
      class="flex max-h-[80dvh] w-[min(30rem,calc(100vw-2rem))] flex-col gap-4 overflow-y-auto"
      :aria-labelledby="titleId"
      :aria-describedby="descriptionId"
    >
      <div>
        <h3 :id="titleId">Portrait for {{ props.name }}</h3>
        <p :id="descriptionId" class="text-sm text-muted-foreground">
          Choose a linked face, or let automatic selection keep a stable portrait. Evidence filters
          do not limit these choices.
        </p>
      </div>
      <p class="text-sm" role="status">
        Current selection: {{ props.mode === 'manual' ? 'Manual' : 'Automatic'
        }}{{ props.selectedFaceId ? '' : ' · No linked face' }}
      </p>
      <Button
        variant="outline"
        :disabled="selection.isPending.value || props.mode !== 'manual'"
        @click="save(null)"
        >Use automatic selection</Button
      >
      <p v-if="selection.isError.value" role="alert" class="text-sm text-destructive">
        Could not confirm the portrait change. Please try again.
      </p>
      <p v-if="query.isPending.value" role="status">Loading linked faces…</p>
      <div v-else-if="query.isError.value" role="alert">
        <p>Could not load linked faces.</p>
        <Button variant="outline" @click="query.refetch()">Retry linked faces</Button>
      </div>
      <p v-else-if="!faces.length">
        No linked faces yet. A portrait will be selected automatically when a face is linked.
      </p>
      <div v-else class="flex flex-wrap gap-3">
        <Button
          v-for="(face, index) in faces"
          :key="face.detection_id"
          variant="outline"
          class="h-auto flex-col gap-2 p-3"
          :disabled="selection.isPending.value"
          :aria-label="`Use linked face ${index + 1} as portrait`"
          :aria-pressed="props.selectedFaceId === face.detection_id"
          @click="save(face.detection_id)"
        >
          <PersonPortrait :name="props.name" :face-id="face.detection_id" class="size-20" />
          <span>{{
            props.selectedFaceId === face.detection_id ? 'Current portrait' : `Face ${index + 1}`
          }}</span>
        </Button>
      </div>
      <Button
        v-if="query.hasNextPage.value"
        variant="outline"
        :disabled="query.isFetchingNextPage.value || selection.isPending.value"
        @click="query.fetchNextPage()"
        >{{ query.isFetchingNextPage.value ? 'Loading…' : 'Load more faces' }}</Button
      >
      <p v-if="selection.isPending.value" role="status">Saving portrait…</p>
      <Button variant="ghost" :disabled="selection.isPending.value" @click="open = false"
        >Close portrait choices</Button
      >
    </PopoverContent>
  </Popover>
</template>
