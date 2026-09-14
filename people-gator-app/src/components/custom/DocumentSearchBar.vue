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
</script>

<template>
  <Card class="sticky top-0 z-20 gap-3 rounded-none py-3">
    <CardContent class="grid w-full grid-cols-3 gap-2 px-3 lg:grid-cols-[minmax(0,1fr)_repeat(3,minmax(0,9rem))]">
      <InputGroup class="col-span-3 w-full rounded-none lg:col-span-1">
        <InputGroupInput v-model="searchTerm" placeholder="Search a person, page or document…" />
        <InputGroupAddon>
          <Search />
        </InputGroupAddon>
        <InputGroupAddon align="inline-end">
          {{ resultCount }} results
        </InputGroupAddon>
      </InputGroup>
      <Select multiple>
        <SelectTrigger class="w-full rounded-none">
          <SelectValue placeholder="Select libraries" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectLabel>Libraries</SelectLabel>
            <SelectItem value="mzk">MZK</SelectItem>
            <SelectItem value="nkp">NKP</SelectItem>
            <SelectItem value="kvkli">KVKLI</SelectItem>
            <SelectItem value="mu">MU</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
      <Select multiple>
        <SelectTrigger class="w-full rounded-none">
          <SelectValue placeholder="Contains data" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectLabel>Data</SelectLabel>
            <SelectItem value="faces">Faces</SelectItem>
            <SelectItem value="names">Names</SelectItem>
            <SelectItem value="nothing">Nothing</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
      <Select multiple>
        <SelectTrigger class="w-full rounded-none">
          <SelectValue placeholder="Select annotation status" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectLabel>Annotation status</SelectLabel>
            <SelectItem value="checked">Checked</SelectItem>
            <SelectItem value="unchecked">Unchecked</SelectItem>
            <SelectItem value="modified">Modified</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
    </CardContent>
  </Card>
</template>
