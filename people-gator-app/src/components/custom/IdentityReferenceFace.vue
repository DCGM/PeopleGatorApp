<script setup lang="ts">
import { ScanFace } from '@lucide/vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { useFaceAlignedCropQuery } from '@/query/faces'
import { useObjectUrl } from '@/composables/object-url'

const props = defineProps<{ faceId: string; label: string }>()
const crop = useFaceAlignedCropQuery(() => props.faceId, 256)
const url = useObjectUrl(() => crop.data.value)
</script>

<template>
  <Avatar role="listitem" class="aspect-square size-auto w-full">
    <AvatarImage :src="url" :alt="label" :loading="crop.isPending.value" class="object-cover" />
    <AvatarFallback :aria-label="`${label}: crop unavailable`">
      <ScanFace aria-hidden="true" /><span class="sr-only">{{ label }}: crop unavailable</span>
    </AvatarFallback>
  </Avatar>
</template>
