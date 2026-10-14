import { defineConfig } from '@hey-api/openapi-ts'

export default defineConfig({
  input: process.env.PEOPLE_GATOR_OPENAPI ?? '../people-gator-api/openapi.json',
  output: 'src/client',
  plugins: ['@hey-api/client-axios'],
})
