<script setup lang="ts">
import type { AvatarImageProps } from 'reka-ui'
import { AvatarImage } from 'reka-ui'
import { reactiveOmit } from '@vueuse/core'
import { computed, ref, useAttrs } from 'vue'

import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const props = defineProps<AvatarImageProps & { loading?: boolean }>()
const attrs = useAttrs()
const imageProps = reactiveOmit(props, 'loading')
const forwardedProps = computed(() => {
  return {
    ...attrs,
    ...imageProps,
    src: props.src,
    class: cn('aspect-square size-full', attrs.class),
  }
})

const loadingStatus = ref<'idle' | 'loading' | 'loaded' | 'error'>('idle')
</script>

<template>
  <Skeleton
    v-if="props.loading || (props.src && (loadingStatus === 'idle' || loadingStatus === 'loading'))"
    data-slot="avatar-image-skeleton"
    aria-hidden="true"
    class="absolute inset-0 z-10 size-full rounded-full"
  />
  <AvatarImage
    data-slot="avatar-image"
    v-bind="forwardedProps"
    @loading-status-change="loadingStatus = $event"
  >
    <slot />
  </AvatarImage>
</template>
