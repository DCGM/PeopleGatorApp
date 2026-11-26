<script setup lang="ts">
import {
  TooltipProvider,
  TooltipRoot,
  TooltipTrigger,
  TooltipPortal,
  TooltipContent,
} from 'reka-ui'
defineProps<{ text: string }>()
</script>
<template>
  <TooltipProvider :delay-duration="200"
    ><TooltipRoot>
      <TooltipTrigger as-child><slot /></TooltipTrigger>
      <TooltipPortal
        ><TooltipContent
          side="top"
          :side-offset="5"
          class="z-50 max-w-xs rounded-md bg-foreground px-3 py-1.5 text-xs text-background shadow-md"
          >{{ text }}</TooltipContent
        ></TooltipPortal
      >
    </TooltipRoot></TooltipProvider
  >
</template>
