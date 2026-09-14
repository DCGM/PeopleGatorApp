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

defineProps<{
  resultCount: number
}>()

const searchTerm = defineModel<string>('searchTerm', { required: true })
const filters = defineModel<string>('filters', { required: true })
</script>

<template>
  <div class="sticky top-0 z-20">
    <Card class="gap-3 rounded-none py-3">
      <CardContent class="grid w-full grid-cols-2 gap-2 px-3 lg:grid-cols-[minmax(0,1fr)_repeat(2,minmax(0,9rem))]">
        <InputGroup class="col-span-2 w-full rounded-none lg:col-span-1">
          <InputGroupInput v-model="searchTerm" placeholder="Search a person or alias…" />
          <InputGroupAddon>
            <Search />
          </InputGroupAddon>
          <InputGroupAddon align="inline-end">{{ resultCount }} results</InputGroupAddon>
        </InputGroup>
        <Select v-model="filters" :multiple="true">
          <SelectTrigger class="w-full rounded-none">
            <SelectValue placeholder="Contains data" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel>Contains data</SelectLabel>
              <SelectItem value="all">Names and faces</SelectItem>
              <SelectItem value="faces">Faces</SelectItem>
              <SelectItem value="names">Names</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <Select v-model="filters" :multiple="true">
          <SelectTrigger class="w-full rounded-none">
            <SelectValue placeholder="Select annotation status" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel>Annotation status</SelectLabel>
              <SelectItem value="fully-annotated">Annotated</SelectItem>
              <SelectItem value="partially-annotated">Partially Annotated</SelectItem>
              <SelectItem value="not-annotated">Not Annotated</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
      </CardContent>
    </Card>
  </div>
</template>
