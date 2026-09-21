<script setup lang="ts">
import { Search } from '@lucide/vue'

import { Card, CardContent } from '@/components/ui/card'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { AssignmentFilter } from '@/viewmodels/assignment'

defineProps<{
  resultCount: number
  hasMoreResults?: boolean
}>()

const searchTerm = defineModel<string>('searchTerm', { required: true })
const assignment = defineModel<AssignmentFilter>('assignment', { required: true })
</script>

<template>
  <Card class="sticky top-13 z-20 gap-3 rounded-none py-3">
    <CardContent
      class="grid w-full grid-cols-2 gap-2 px-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,11rem)]"
    >
      <InputGroup class="col-span-2 w-full rounded-none lg:col-span-1">
        <InputGroupInput v-model="searchTerm" placeholder="Search a person, page or document…" />
        <InputGroupAddon>
          <Search />
        </InputGroupAddon>
        <InputGroupAddon align="inline-end" class="min-w-20 justify-end tabular-nums">
          {{ resultCount }}{{ hasMoreResults ? '+' : '' }} results
        </InputGroupAddon>
      </InputGroup>
      <Select v-model="assignment">
        <SelectTrigger class="w-full rounded-none">
          <SelectValue placeholder="Assignment" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectLabel>Assignment</SelectLabel>
            <SelectItem value="all">All pages</SelectItem>
            <SelectItem value="faces">Assigned faces</SelectItem>
            <SelectItem value="mentions">Assigned mentions</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
    </CardContent>
  </Card>
</template>
