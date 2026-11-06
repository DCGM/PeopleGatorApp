import { createApp } from 'vue'
import { initializeAuthentication } from './query/auth'
import './style.css'

try {
  await initializeAuthentication()
  await import('./main')
} catch {
  // Never retry automatically after a failed callback. A new explicit sign-in
  // creates fresh state/nonce/PKCE rather than looping with a consumed code.
  history.replaceState(null, '', '/login.html?error=callback')
  const { default: LoginGateway } = await import('./views/LoginGateway.vue')
  createApp(LoginGateway).mount('#app')
}
