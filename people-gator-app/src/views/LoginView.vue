<script setup lang="ts">
import { CircleAlert } from '@lucide/vue'
import { isAxiosError } from 'axios'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { appConfig } from '@/app-config'
import PeopleGatorIcon from '@/components/custom/PeopleGatorIcon'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { login, loginAsPublic } from '@/query/client'
import { redirectTarget } from '@/router/auth'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const pending = ref(false)
const error = ref('')

async function signIn(request: () => Promise<unknown>) {
  pending.value = true
  error.value = ''
  try {
    await request()
    await router.replace(redirectTarget(route.query.redirect))
  } catch (cause) {
    const status = isAxiosError(cause) ? cause.response?.status : undefined
    error.value =
      status === 401
        ? 'Wrong username or password.'
        : status === 403
          ? 'This account has no access.'
          : 'Could not sign in. Try again.'
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <main class="flex min-h-dvh items-center justify-center p-4">
    <Card class="w-full max-w-sm">
      <CardHeader class="justify-items-center text-center">
        <PeopleGatorIcon aria-hidden="true" class="size-12 text-primary" stroke-width="1" />
        <CardTitle class="font-heading text-xl font-light">Sign in to PeopleGator</CardTitle>
      </CardHeader>
      <CardContent>
        <form @submit.prevent="signIn(() => login(username, password))">
          <FieldGroup class="gap-4">
            <Alert v-if="error" variant="destructive">
              <CircleAlert aria-hidden="true" />
              <AlertDescription>{{ error }}</AlertDescription>
            </Alert>
            <Field>
              <FieldLabel for="login-username">Username</FieldLabel>
              <Input
                id="login-username"
                v-model="username"
                name="username"
                autocomplete="username"
                autocapitalize="none"
                required
                autofocus
              />
            </Field>
            <Field>
              <FieldLabel for="login-password">Password</FieldLabel>
              <Input
                id="login-password"
                v-model="password"
                name="password"
                type="password"
                autocomplete="current-password"
                required
              />
            </Field>
            <Field>
              <Button type="submit" :disabled="pending">Sign in</Button>
              <Button
                v-if="appConfig.publicLogin"
                type="button"
                variant="outline"
                :disabled="pending"
                @click="signIn(loginAsPublic)"
              >
                Continue as guest
              </Button>
            </Field>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  </main>
</template>
