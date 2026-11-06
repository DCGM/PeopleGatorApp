import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import type { Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import tailwindcss from '@tailwindcss/vite'
import vueDevTools from 'vite-plugin-vue-devtools'

const swaggerEntry: Plugin = {
  name: 'swagger-session-entry',
  configureServer(server) {
    server.middlewares.use((request, _response, next) => {
      if (request.url?.split('?')[0] === '/swagger-auth.js')
        request.url = request.url.replace('/swagger-auth.js', '/src/swagger-auth.ts')
      next()
    })
  },
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const allowedHosts = env.ALLOWED_VITE_HOSTS?.split(',')
    .map((host) => host.trim())
    .filter(Boolean)

  const apiTarget = env.API_PROXY_TARGET || undefined
  const authTarget = env.AUTH_PROXY_TARGET || undefined
  return {
    build: {
      rollupOptions: {
        output: {
          entryFileNames: (entry) =>
            entry.name === 'swagger-auth' ? 'swagger-auth.js' : 'assets/[name]-[hash].js',
        },
        input: {
          app: fileURLToPath(new URL('./index.html', import.meta.url)),
          login: fileURLToPath(new URL('./login.html', import.meta.url)),
          callback: fileURLToPath(new URL('./auth-callback.html', import.meta.url)),
          'swagger-auth': fileURLToPath(new URL('./src/swagger-auth.ts', import.meta.url)),
        },
      },
    },
    plugins: [swaggerEntry, vue(), vueJsx(), tailwindcss(), vueDevTools()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      proxy: {
        ...(authTarget
          ? Object.fromEntries(
              ['/token/', '/.well-known/', '/auth/health'].map((path) => [
                path,
                { target: authTarget, changeOrigin: true },
              ]),
            )
          : {}),
        ...(apiTarget
          ? Object.fromEntries(
              ['/api', '/docs', '/redoc', '/openapi.json'].map((path) => [
                path,
                { target: apiTarget, changeOrigin: true },
              ]),
            )
          : {}),
      },
      allowedHosts: allowedHosts && allowedHosts.length > 0 ? allowedHosts : ['localhost'],
    },
  }
})
