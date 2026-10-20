<script setup lang="ts">
import { computed } from 'vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { useFaceAlignedCropQuery } from '@/query/faces'
import { useObjectUrl } from '@/composables/object-url'

const props = defineProps<{ name: string; faceId?: string | null; largeInitials?: boolean }>()
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
      :loading="Boolean(props.faceId) && !url && crop.isPending.value"
      class="object-cover grayscale"
    />
    <AvatarFallback class="font-serif" :class="props.largeInitials && 'text-2xl'">{{
      initials
    }}</AvatarFallback>
  </Avatar>
</template>
