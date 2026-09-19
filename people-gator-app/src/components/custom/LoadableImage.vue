<script setup lang="ts">
import {
  computed,
  nextTick,
  onMounted,
  ref,
  useTemplateRef,
  watch,
  type HTMLAttributes,
} from 'vue'

import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

type ImageState = 'idle' | 'loading' | 'loaded' | 'error'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  src?: string | null
  alt: string
  loading?: boolean
  class?: HTMLAttributes['class']
  imageClass?: HTMLAttributes['class']
  skeletonClass?: HTMLAttributes['class']
}>()

const emit = defineEmits<{
  load: [event: Event]
  error: [event: Event]
}>()

const image = useTemplateRef<HTMLImageElement>('image')
const state = ref<ImageState>(props.src ? 'loading' : 'idle')
const isLoading = computed(() => props.loading || state.value === 'loading')

function syncCompletedImage() {
  const element = image.value
  if (!props.src || !element?.complete) return
  state.value = element.naturalWidth > 0 ? 'loaded' : 'error'
}

function handleLoad(event: Event) {
  state.value = 'loaded'
  emit('load', event)
}

function handleError(event: Event) {
  state.value = 'error'
  emit('error', event)
}

watch(
  () => props.src,
  async (src) => {
    state.value = src ? 'loading' : 'idle'
    await nextTick()
    syncCompletedImage()
  },
)

onMounted(syncCompletedImage)
</script>

<template>
  <div
    data-slot="loadable-image"
    :data-state="isLoading ? 'loading' : state"
    :aria-busy="isLoading"
    :class="cn('relative overflow-hidden', props.class)"
  >
    <Skeleton
      v-if="isLoading"
      data-slot="image-skeleton"
      aria-hidden="true"
      :class="cn('absolute inset-0 size-full rounded-none', props.skeletonClass)"
    />
    <img
      v-if="props.src"
      ref="image"
      v-bind="$attrs"
      :src="props.src"
      :alt="props.alt"
      :class="
        cn(
          'size-full transition-opacity duration-200',
          state === 'loaded' ? 'opacity-100' : 'opacity-0',
          props.imageClass,
        )
      "
      @load="handleLoad"
      @error="handleError"
    />
    <slot
      v-if="!isLoading && (state === 'idle' || state === 'error')"
      name="fallback"
      :state="state"
    />
  </div>
</template>
