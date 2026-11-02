<script setup lang="ts">
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
import LoadableImage from './LoadableImage.vue'
import { linkMetadata, linkTooltip } from '@/lib/entity-links'
import { useObjectUrl } from '@/composables/object-url'
import { useFaceAlignedCropQuery } from '@/query/faces'
import type { ScanFaceItem } from '@/viewmodels/scan-faces'

const props = defineProps<{
  item: ScanFaceItem
  selected?: boolean
  /** Off-page faces open their own page; on-page faces select in place. */
  to?: RouteLocationRaw
}>()
defineEmits<{ select: [] }>()
const crop = useFaceAlignedCropQuery(() => props.item.face.detection_id, 256)
const url = useObjectUrl(() => crop.data.value)
const link = computed(() => linkMetadata(props.item.face))
const name = computed(() =>
  props.item.face.entity_id ? (props.item.personName ?? 'Linked person') : 'Unassigned',
)
const pageLabel = computed(() =>
  props.item.onPage
    ? undefined
    : props.item.page?.page_number != null
      ? `p. ${props.item.page.page_number}`
      : 'Other page',
)
const label = computed(
  () =>
    `${props.item.onPage ? 'Select' : 'Open'} face: ${name.value}${pageLabel.value ? `, ${pageLabel.value}` : ''}, ${linkTooltip(link.value)}`,
)
</script>

<template>
  <component
    :is="to ? 'RouterLink' : 'button'"
    :to="to"
    :type="to ? undefined : 'button'"
    class="group relative block size-16 shrink-0 rounded-md border-2 bg-muted outline-none transition-[border-color,box-shadow] hover:border-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    :class="selected ? 'border-secondary ring-2 ring-secondary ring-offset-2' : 'border-border'"
    :aria-label="label"
    :aria-pressed="to ? undefined : selected"
    :aria-current="selected ? 'true' : undefined"
    :title="pageLabel ? `${name} · ${pageLabel}` : name"
    @click="!to && $emit('select')"
  >
    <LoadableImage
      :src="url"
      :loading="crop.isPending.value"
      :alt="name"
      class="size-full rounded-[calc(var(--radius-md)-2px)]"
      image-class="size-full object-cover grayscale"
    />
    <small
      v-if="pageLabel"
      class="absolute inset-x-0 bottom-0 truncate rounded-b-[calc(var(--radius-md)-2px)] bg-background/85 px-1 text-center text-[0.625rem] leading-4"
      aria-hidden="true"
      >{{ pageLabel }}</small
    >
    <EntityLinkStateBadge
      v-bind="link"
      :focusable="false"
      :tooltip="false"
      compact
      class="absolute -right-1.5 -top-1.5 shadow-sm"
    />
  </component>
</template>
