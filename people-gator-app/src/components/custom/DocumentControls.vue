<script setup lang="ts">
import LinkStatePanel from './LinkStatePanel.vue'
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
    class="flex select-none flex-wrap items-center justify-center gap-2 [&_button:disabled]:bg-white/90 [&_button:disabled]:backdrop-blur-[50px] [&_button:disabled]:text-slate-400 [&_button:disabled]:opacity-100"
  >
    <ButtonGroup class="shrink-0 drop-shadow-md">
      <Button
        variant="outline"
        size="icon-sm"
        aria-label="Previous line"
        title="Previous line"
        :disabled="lineCount === 0 || selectedLineIndex <= 0"
        @click="$emit('previous-line')"
      >
        <ChevronUp />
      </Button>
      <ButtonGroupText size="icon-sm" class="font-mono text-sm px-1 py-0.5 bg-background">
        <Rows3 class="size-3" /> Line
      </ButtonGroupText>
      <Button
        variant="outline"
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
        variant="outline"
        size="icon-sm"
        aria-label="Previous face"
        title="Previous face"
        :disabled="selectedFaceIndex <= 0"
        @click="$emit('previous-face')"
      >
        <ChevronLeft />
      </Button>
      <ButtonGroupText size="icon-sm" class="font-mono text-sm px-1 py-0.5 bg-background">
        <ScanFace class="size-3" /> Face
      </ButtonGroupText>
      <Button
        variant="outline"
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
        variant="outline"
        size="icon-sm"
        aria-label="Zoom out"
        title="Zoom out"
        :disabled="zoomPercent <= minimumZoomPercent"
        @click="$emit('set-zoom', 'out')"
      >
        <Minus />
      </Button>
      <ButtonGroupText class="font-mono text-sm justify-center px-1 py-0.5 min-w-9 bg-background">
        {{ zoomPercent }}%
      </ButtonGroupText>
      <Button
        variant="outline"
        size="icon-sm"
        aria-label="Zoom in"
        title="Zoom in"
        :disabled="zoomPercent >= maximumZoomPercent"
        @click="$emit('set-zoom', 'in')"
      >
        <Plus />
      </Button>
      <Button
        variant="outline"
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
        variant="outline"
        size="sm"
        class="font-mono text-sm"
        :class="
          showBadgeNames
            ? 'bg-muted text-foreground'
            : 'bg-white/90 backdrop-blur-[50px] text-muted-foreground dark:bg-white/90 dark:text-slate-500'
        "
        :aria-label="showBadgeNames ? 'Hide overlay badge names' : 'Show overlay badge names'"
        :title="showBadgeNames ? 'Hide overlay badge names' : 'Show overlay badge names'"
        :aria-pressed="showBadgeNames"
        @click="$emit('toggle-badge-names')"
      >
        <Tags />
        Names
      </Button>
    </ButtonGroup>

    <LinkStatePanel v-model="linkStates" />

    <ButtonGroup class="shrink-0 drop-shadow-md" aria-label="Translation">
      <Button
        v-for="option in translationOptions"
        :key="option"
        variant="outline"
        size="sm"
        class="font-mono text-sm uppercase"
        :class="
          (option === 'off' ? !isTranslationOpen : isTranslationOpen && selectedLanguage === option)
            ? 'bg-muted font-semibold text-foreground'
            : 'bg-white/90 backdrop-blur-[50px] text-muted-foreground hover:text-foreground dark:bg-white/90 dark:text-slate-500'
        "
        :aria-pressed="
          option === 'off' ? !isTranslationOpen : isTranslationOpen && selectedLanguage === option
        "
        @click="$emit('select-translation', option)"
      >
        <Languages
          v-if="option === 'off'"
          class="size-[1.25em] transition-colors"
          :class="isTranslationOpen ? 'text-secondary' : 'text-muted-foreground/50'"
        />
        {{ option }}
      </Button>
    </ButtonGroup>
  </div>
</template>
