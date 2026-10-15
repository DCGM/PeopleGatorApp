<script setup lang="ts">
import EntityLinkStateFilter from './EntityLinkStateFilter.vue'
import type { EntityLinkState } from '@/client'
const linkStates = defineModel<EntityLinkState[]>('linkStates', { default: () => [] })
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Languages,
  LocateFixed,
  Minus,
  Plus,
  Rows3,
  ScanFace,
  Tags,
} from '@lucide/vue'

import type { Language } from '@/client'
import { Button } from '@/components/ui/button'
import { ButtonGroup, ButtonGroupText } from '@/components/ui/button-group'

defineProps<{
  selectedLineIndex: number
  lineCount: number
  selectedFaceIndex: number
  faceCount: number
  zoomPercent: number
  minimumZoomPercent: number
  maximumZoomPercent: number
  translationOptions: readonly ('off' | Language)[]
  isTranslationOpen: boolean
  selectedLanguage: Language
  showBadgeNames: boolean
}>()

defineEmits<{
  'previous-line': []
  'next-line': []
  'previous-face': []
  'next-face': []
  'set-zoom': [direction: 'in' | 'out']
  'reset-view': []
  'select-translation': [language: Language | 'off']
  'toggle-badge-names': []
}>()
</script>

<template>
  <div
    role="toolbar"
    aria-label="Scan tools"
    class="flex max-w-full select-none flex-row flex-wrap items-center justify-center gap-2"
  >
    <ButtonGroup class="shrink-0 drop-shadow-md">
      <Button
        variant="secondary"
        size="icon-sm"
        aria-label="Previous line"
        title="Previous line"
        :disabled="lineCount === 0 || selectedLineIndex <= 0"
        @click="$emit('previous-line')"
      >
        <ChevronUp />
      </Button>
      <ButtonGroupText size="icon-sm" class="font-mono text-sm px-1 py-0.5">
        <Rows3 class="size-3" /> Line
      </ButtonGroupText>
      <Button
        variant="secondary"
        size="icon-sm"
        aria-label="Next line"
        title="Next line"
        :disabled="lineCount === 0 || selectedLineIndex >= lineCount - 1"
        @click="$emit('next-line')"
      >
        <ChevronDown />
      </Button>
    </ButtonGroup>

    <ButtonGroup class="shrink-0 drop-shadow-md">
      <Button
        variant="secondary"
        size="icon-sm"
        aria-label="Previous face"
        title="Previous face"
        :disabled="selectedFaceIndex <= 0"
        @click="$emit('previous-face')"
      >
        <ChevronLeft />
      </Button>
      <ButtonGroupText size="icon-sm" class="font-mono text-sm px-1 py-0.5">
        <ScanFace class="size-3" /> Face
      </ButtonGroupText>
      <Button
        variant="secondary"
        size="icon-sm"
        aria-label="Next face"
        title="Next face"
        :disabled="faceCount === 0 || selectedFaceIndex === faceCount - 1"
        @click="$emit('next-face')"
      >
        <ChevronRight />
      </Button>
    </ButtonGroup>

    <ButtonGroup class="shrink-0 drop-shadow-md">
      <Button
        variant="secondary"
        size="icon-sm"
        aria-label="Zoom out"
        title="Zoom out"
        :disabled="zoomPercent <= minimumZoomPercent"
        @click="$emit('set-zoom', 'out')"
      >
        <Minus />
      </Button>
      <ButtonGroupText class="font-mono text-sm justify-center px-1 py-0.5 min-w-9">
        {{ zoomPercent }}%
      </ButtonGroupText>
      <Button
        variant="secondary"
        size="icon-sm"
        aria-label="Zoom in"
        title="Zoom in"
        :disabled="zoomPercent >= maximumZoomPercent"
        @click="$emit('set-zoom', 'in')"
      >
        <Plus />
      </Button>
      <Button
        variant="secondary"
        size="icon-sm"
        aria-label="Center page"
        title="Center page"
        @click="$emit('reset-view')"
      >
        <LocateFixed />
      </Button>
    </ButtonGroup>

    <ButtonGroup class="shrink-0 drop-shadow-md">
      <Button
        :variant="showBadgeNames ? 'default' : 'secondary'"
        size="sm"
        class="font-mono text-sm"
        :aria-label="showBadgeNames ? 'Hide overlay badge names' : 'Show overlay badge names'"
        :title="showBadgeNames ? 'Hide overlay badge names' : 'Show overlay badge names'"
        :aria-pressed="showBadgeNames"
        @click="$emit('toggle-badge-names')"
      >
        <Tags />
        Names
      </Button>
    </ButtonGroup>

    <EntityLinkStateFilter v-model="linkStates" toolbar />

    <ButtonGroup class="shrink-0 drop-shadow-md" aria-label="Translation">
      <Button
        v-for="option in translationOptions"
        :key="option"
        :variant="
          (option === 'off' ? !isTranslationOpen : isTranslationOpen && selectedLanguage === option)
            ? 'default'
            : 'secondary'
        "
        size="sm"
        class="font-mono text-sm uppercase"
        :aria-pressed="
          option === 'off' ? !isTranslationOpen : isTranslationOpen && selectedLanguage === option
        "
        @click="$emit('select-translation', option)"
      >
        <Languages v-if="option === 'off'" class="size-[1.25em]" />
        {{ option }}
      </Button>
    </ButtonGroup>
  </div>
</template>
