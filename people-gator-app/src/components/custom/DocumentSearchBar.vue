<script setup lang="ts">
import { Search } from '@lucide/vue'

import { Card, CardContent } from '@/components/ui/card'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'

defineProps<{
  resultCount: number
  hasMoreResults?: boolean
}>()

const searchTerm = defineModel<string>('searchTerm', { required: true })
</script>

<template>
  <Card class="sticky top-0 z-20 gap-3 rounded-none py-3">
    <CardContent class="px-3">
      <InputGroup class="w-full rounded-none">
        <InputGroupInput v-model="searchTerm" placeholder="Search a person, page or document…" />
        <InputGroupAddon>
          <Search />
        </InputGroupAddon>
        <InputGroupAddon align="inline-end">
          {{ resultCount }}{{ hasMoreResults ? '+' : '' }} results
        </InputGroupAddon>
      </InputGroup>
    </CardContent>
  </Card>
</template>
