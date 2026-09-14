<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'

import { AspectRatio } from '@/components/ui/aspect-ratio'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'

const props = defineProps<{
  library: string
  documentUuid: string
  pageUuid: string
  names: readonly string[]
}>()

function compactUuid(uuid: string) {
  const hex = uuid.replace(/-/g, '')
  const bytes = hex.match(/.{2}/g)

  if (!bytes || bytes.length !== 16) return uuid

  const binary = String.fromCharCode(...bytes.map((byte: string) => Number.parseInt(byte, 16)))
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function scanThumbnail(pageUuid: string) {
  const seed = Array.from(pageUuid).reduce((total, character) => total + character.charCodeAt(0), 0)
  const lines = Array.from({ length: 11 }, (_, index) => {
    const width = 118 - ((index * 17 + seed) % 35)
    return `<rect x="22" y="${48 + index * 13}" width="${width}" height="2" rx="1"/>`
  }).join('')
  const pageLabel = compactUuid(pageUuid).slice(0, 8)
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="180" height="240" viewBox="0 0 180 240"><rect width="180" height="240" fill="#d8c8a8"/><rect x="12" y="10" width="156" height="220" fill="#f4ead2" stroke="#8d7956"/><text x="90" y="31" text-anchor="middle" font-family="serif" font-size="10" fill="#62543e">ARCHIVE · ${pageLabel}</text><g fill="#8b795a" opacity=".72">${lines}</g><path d="M25 204c28-18 47 13 72-4s35 4 53-8" fill="none" stroke="#786344" stroke-width="2"/><text x="125" y="218" font-family="serif" font-size="8" fill="#786344">${pageLabel}</text></svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}
</script>

<template>
  <Card
    class="h-full gap-2 overflow-hidden rounded-none border-0 bg-transparent py-0 text-muted-foreground shadow-none transition-transform group-hover:text-primary group-focus:text-primary">
    <CardHeader class="gap-0 px-0">
      <AspectRatio :ratio="210 / 297" class="overflow-hidden bg-muted">
        <img :src="scanThumbnail(props.pageUuid)" :alt="`Scan ${props.pageUuid} from document ${props.documentUuid}`"
          class="h-full w-full object-cover duration-300 ease-out group-hover:scale-105 group-focus:scale-102">
      </AspectRatio>
    </CardHeader>
    <CardContent class="px-0">
      <small class="truncate" :title="props.pageUuid">
        <span class="font-bold text-secondary">{{ props.library }} · </span>
        {{ compactUuid(props.pageUuid) }}
      </small>
    </CardContent>
    <CardFooter class="gap-1 px-0">
      <small class="flex-1 truncate font-heading">
        {{ props.names.slice(0, 2).join(', ') }}
      </small>
      <small v-if="props.names.length > 2" class="whitespace-nowrap text-secondary">
        +{{ props.names.length - 2 }} more
      </small>
      <ChevronRight
        class="size-4 shrink-0 transition-all duration-200 group-hover:translate-x-1 group-focus:-translate-x-1"
        aria-hidden="true" />
    </CardFooter>
  </Card>
</template>
