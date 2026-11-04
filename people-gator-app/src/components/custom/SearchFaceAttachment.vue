<script setup lang="ts">
import { X } from '@lucide/vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { InputGroupButton } from '@/components/ui/input-group'
import { useObjectUrl } from '@/composables/object-url'
import { useFaceAlignedCropQuery } from '@/query/faces'

const props = defineProps<{ faceId: string }>()
defineEmits<{ remove: [] }>()
const crop = useFaceAlignedCropQuery(() => props.faceId, 96)
const url = useObjectUrl(() => crop.data.value)
</script>

<template>
  <span
    class="flex shrink-0 items-center gap-1.5 rounded-full border py-0.5 pl-0.5 text-xs text-foreground"
    data-search-face
    :data-face-id="faceId"
  >
    <Avatar class="size-6">
      <AvatarImage :src="url" alt="" class="object-cover grayscale" />
      <AvatarFallback class="text-[0.625rem]">F</AvatarFallback>
    </Avatar>
    Face
    <InputGroupButton
      size="icon-xs"
      class="rounded-full"
      aria-label="Remove search face"
      @click="$emit('remove')"
      ><X aria-hidden="true"
    /></InputGroupButton>
  </span>
</template>
