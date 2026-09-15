<script setup lang="ts">
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
} from '@lucide/vue'

import type { TranslationLanguage } from '@/components/custom/document-page.types'
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
  translationOptions: readonly ('off' | TranslationLanguage)[]
  isTranslationOpen: boolean
  selectedLanguage: TranslationLanguage
  contextLineCount: number
  maximumContextLineCount: number
}>()

defineEmits<{
  'previous-line': []
  'next-line': []
  'previous-face': []
  'next-face': []
  'set-zoom': [direction: 'in' | 'out']
  'reset-view': []
  'select-translation': [language: TranslationLanguage | 'off']
  'change-context': [direction: 'decrease' | 'increase']
}>()
</script>

<template>
  <div class="flex min-w-max select-none items-center justify-center gap-2 px-2">
    <ButtonGroup class="shrink-0">
      <Button variant="outline" size="icon-sm" aria-label="Previous line" title="Previous line"
        :disabled="selectedLineIndex === 0" @click="$emit('previous-line')">
        <ChevronUp />
      </Button>
      <ButtonGroupText size="icon-sm" class="font-mono text-sm px-1 py-0.5 bg-background">
        <Rows3 class="size-3" /> Line
      </ButtonGroupText>
      <Button variant="outline" size="icon-sm" aria-label="Next line" title="Next line"
        :disabled="selectedLineIndex === lineCount - 1" @click="$emit('next-line')">
        <ChevronDown />
      </Button>
    </ButtonGroup>

    <ButtonGroup class="shrink-0">
      <Button variant="outline" size="icon-sm" aria-label="Previous face" title="Previous face"
        :disabled="selectedFaceIndex === 0" @click="$emit('previous-face')">
        <ChevronLeft />
      </Button>
      <ButtonGroupText size="icon-sm" class="font-mono text-sm px-1 py-0.5 bg-background">
        <ScanFace class="size-3" /> Face
      </ButtonGroupText>
      <Button variant="outline" size="icon-sm" aria-label="Next face" title="Next face"
        :disabled="selectedFaceIndex === faceCount - 1" @click="$emit('next-face')">
        <ChevronRight />
      </Button>
    </ButtonGroup>

    <ButtonGroup class="shrink-0">
      <Button variant="outline" size="icon-sm" aria-label="Zoom out" title="Zoom out"
        :disabled="zoomPercent <= minimumZoomPercent" @click="$emit('set-zoom', 'out')">
        <Minus />
      </Button>
      <ButtonGroupText class="font-mono text-sm justify-center px-1 py-0.5 min-w-9 bg-background">
        {{ zoomPercent }}%
      </ButtonGroupText>
      <Button variant="outline" size="icon-sm" aria-label="Zoom in" title="Zoom in"
        :disabled="zoomPercent >= maximumZoomPercent" @click="$emit('set-zoom', 'in')">
        <Plus />
      </Button>
      <Button variant="outline" size="icon-sm" aria-label="Center page" title="Center page"
        @click="$emit('reset-view')">
        <LocateFixed />
      </Button>
    </ButtonGroup>

    <ButtonGroup class="shrink-0" aria-label="Translation">
      <Button v-for="option in translationOptions" :key="option" variant="outline" size="sm"
        class="font-mono text-sm uppercase" :class="(option === 'off' ? !isTranslationOpen : isTranslationOpen && selectedLanguage === option)
          ? 'bg-muted font-semibold text-foreground'
          : 'text-muted-foreground hover:text-foreground'"
        :aria-pressed="option === 'off' ? !isTranslationOpen : isTranslationOpen && selectedLanguage === option"
        @click="$emit('select-translation', option)">
        <Languages v-if="option === 'off'" class="size-[1.25em] transition-colors"
          :class="isTranslationOpen ? 'text-secondary' : 'text-muted-foreground/50'" />
        {{ option }}
      </Button>
    </ButtonGroup>

    <ButtonGroup class="shrink-0">
      <Button variant="outline" size="icon-sm" aria-label="Show fewer context lines" title="Show fewer context lines"
        :disabled="contextLineCount === 1" @click="$emit('change-context', 'decrease')">
        <Minus />
      </Button>
      <ButtonGroupText class="min-w-16 justify-center bg-background px-1.5 font-mono text-sm font-normal">
        {{ contextLineCount }} lines
      </ButtonGroupText>
      <Button variant="outline" size="icon-sm" aria-label="Show more context lines" title="Show more context lines"
        :disabled="contextLineCount >= maximumContextLineCount" @click="$emit('change-context', 'increase')">
        <Plus />
      </Button>
    </ButtonGroup>
  </div>
</template>
