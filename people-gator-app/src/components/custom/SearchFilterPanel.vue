<script setup lang="ts">
import { computed, ref, useSlots } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Search, SlidersHorizontal, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'

const props = withDefaults(
  defineProps<{
    label: string
    placeholder?: string
    resultCount?: number
    hasMoreResults?: boolean
    filtersOnly?: boolean
    disabled?: boolean
    hideFilters?: boolean
  }>(),
  { placeholder: 'Search…' },
)
const searchTerm = defineModel<string>({ default: '' })
const slots = useSlots()
const hasFilters = computed(() => !!slots.default && !props.hideFilters)
const input = ref<InstanceType<typeof InputGroupInput>>()
defineExpose({ focus: () => (input.value?.$el as HTMLInputElement)?.focus() })
const desktop = useMediaQuery('(min-width: 640px)')
const mobileOpen = ref(false)
const open = computed({
  get: () => desktop.value || mobileOpen.value,
  set: (value) => {
    mobileOpen.value = value
  },
})
</script>

<template>
  <Collapsible
    v-model:open="open"
    class="search-filter-panel flex w-full min-w-0 flex-row flex-wrap items-start gap-y-2"
    :aria-label="`${label} panel`"
  >
    <div
      v-if="!filtersOnly"
      class="search-controls flex min-w-0 basis-full items-center gap-2"
      :class="hasFilters ? 'sm:basis-2/3 sm:pr-2 lg:basis-1/2' : 'sm:basis-full'"
    >
      <InputGroup class="min-w-0 flex-1">
        <InputGroupInput
          ref="input"
          :disabled="disabled"
          v-model="searchTerm"
          :aria-label="label"
          :placeholder="placeholder"
        />
        <InputGroupAddon><Search aria-hidden="true" /></InputGroupAddon>
        <InputGroupAddon align="inline-end">
          <InputGroupButton
            v-if="searchTerm"
            size="icon-sm"
            :aria-label="`Clear ${label.toLowerCase()}`"
            @click="searchTerm = ''"
            ><X aria-hidden="true"
          /></InputGroupButton>
        </InputGroupAddon>
      </InputGroup>
      <CollapsibleTrigger v-if="hasFilters && !desktop" as-child>
        <Button
          type="button"
          variant="outline"
          size="icon"
          :aria-label="mobileOpen ? 'Hide filters' : 'Show filters'"
          ><SlidersHorizontal aria-hidden="true"
        /></Button>
      </CollapsibleTrigger>
    </div>
    <CollapsibleTrigger v-else-if="!desktop" as-child>
      <Button
        type="button"
        variant="outline"
        size="icon"
        :aria-label="mobileOpen ? 'Hide filters' : 'Show filters'"
        ><SlidersHorizontal aria-hidden="true"
      /></Button>
    </CollapsibleTrigger>
    <CollapsibleContent
      v-if="hasFilters"
      class="filter-controls flex min-w-0 basis-full flex-row flex-wrap items-start gap-2 sm:basis-1/3 lg:basis-1/2"
      :class="filtersOnly && 'sm:basis-full lg:basis-full'"
      :aria-label="`${label} filter controls`"
    >
      <slot />
    </CollapsibleContent>
  </Collapsible>
  <p v-if="resultCount !== undefined" class="mt-2" role="status">
    {{ resultCount }}{{ hasMoreResults ? '+' : '' }} results
  </p>
</template>
