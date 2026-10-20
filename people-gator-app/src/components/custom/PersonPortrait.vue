<script setup lang="ts">
import { computed } from 'vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { useFaceAlignedCropQuery } from '@/query/faces'
import { useObjectUrl } from '@/composables/object-url'

const props = defineProps<{ name: string; faceId?: string | null }>()
const crop = useFaceAlignedCropQuery(() => props.faceId ?? '', 256)
const url = useObjectUrl(() => (props.faceId ? crop.data.value : undefined))
const initials = computed(() =>
  props.name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 3)
    .join(''),
)
</script>

<template>
  <Avatar>
    <AvatarImage
      :key="props.faceId ?? ''"
      :src="url"
      :alt="props.name"
      :loading="Boolean(props.faceId) && crop.isFetching.value"
      class="object-cover grayscale"
    />
    <AvatarFallback class="font-serif">{{ initials }}</AvatarFallback>
  </Avatar>
</template>
