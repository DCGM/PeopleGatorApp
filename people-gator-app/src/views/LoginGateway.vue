<script setup lang="ts">
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { login, safeReturnPath } from '@/query/auth'

const previewAccount = /^pr-\d+\.preview\.peoplegator\.dev$/.test(location.hostname)
const username = ref(previewAccount ? 'test' : '')
const password = ref(previewAccount ? 'test' : '')
const busy = ref(false)
const params = new URLSearchParams(location.search)
const message = ref(params.has('expired') ? 'Your session ended. Sign in again.' : '')
async function submit() {
  busy.value = true
  message.value = ''
  try {
    await login(username.value, password.value)
    password.value = ''
    location.replace(safeReturnPath(params.get('return')))
  } catch (error) {
    message.value = error instanceof Error ? error.message : 'Unable to sign in. Try again.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="min-h-screen bg-background px-6 py-16 text-foreground">
    <div class="mx-auto flex w-full max-w-sm flex-col gap-6">
      <p class="text-muted-foreground">PeopleGator</p>
      <h1 class="text-2xl font-semibold">Sign in</h1>
      <form class="flex flex-col gap-4" @submit.prevent="submit">
        <div class="flex flex-col gap-2">
          <Label for="username">Username</Label>
          <Input
            id="username"
            v-model="username"
            name="username"
            autocomplete="username"
            required
          />
        </div>
        <div class="flex flex-col gap-2">
          <Label for="password">Password</Label>
          <Input
            id="password"
            v-model="password"
            name="password"
            type="password"
            autocomplete="current-password"
            required
          />
        </div>
        <p v-if="message" role="alert">{{ message }}</p>
        <Button type="submit" :disabled="busy">{{ busy ? 'Signing in…' : 'Sign in' }}</Button>
      </form>
    </div>
  </main>
</template>
