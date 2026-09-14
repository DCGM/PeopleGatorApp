import { defineConfig } from '@hey-api/openapi-ts'

export default defineConfig({
  input: 'https://dev.people-gator.capturemyhand.com/openapi.json',
  output: 'src/client',
  plugins: ['@hey-api/client-axios'],
})
