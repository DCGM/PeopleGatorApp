/** Provider-neutral browser authentication; protocol mechanics belong to OIDC libraries. */
import {
  ErrorResponse,
  InMemoryWebStorage,
  UserManager,
  WebStorageStateStore,
} from 'oidc-client-ts'
import { createRemoteJWKSet, jwtVerify } from 'jose'
import type { User } from 'oidc-client-ts'

export interface AuthenticationProvider {
  initialize(): Promise<void>
  accessToken(): Promise<string | undefined>
  signIn(returnTo: string, silent?: boolean): Promise<void>
  signOut(): Promise<void>
  finishSignOut(): Promise<void>
}

export function safeReturnPath(value: unknown): string {
  if (
    typeof value !== 'string' ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    /[\\\r\n]/.test(value)
  )
    return '/'
  const url = new URL(value, location.origin)
  return url.origin === location.origin &&
    !['/login.html', '/staging-login.html', '/auth-callback.html'].includes(url.pathname)
    ? url.pathname + url.search + url.hash
    : '/'
}

function target(state: unknown): string {
  return safeReturnPath(
    state && typeof state === 'object' && 'returnTo' in state ? state.returnTo : '/',
  )
}

export class OidcAuthenticationProvider implements AuthenticationProvider {
  private readonly manager: UserManager
  private readonly hint: string
  private readonly recovering: string
  private initialized?: Promise<void>
  private pendingToken?: Promise<string | undefined>
  private navigating = false
  private signingKeys?: ReturnType<typeof createRemoteJWKSet>

  constructor(
    readonly authority: string,
    readonly clientId: string,
    scope: string,
  ) {
    this.hint = `people-gator.oidc-session:${authority}:${clientId}`
    this.recovering = this.hint + ':recovering'
    this.manager = new UserManager({
      authority,
      client_id: clientId,
      scope,
      redirect_uri: location.origin + '/auth-callback.html',
      post_logout_redirect_uri: location.origin + '/login.html',
      response_type: 'code',
      response_mode: 'query',
      disablePKCE: false,
      loadUserInfo: false,
      automaticSilentRenew: false,
      monitorSession: false,
      userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
      // Only short-lived state/nonce/PKCE transactions survive navigation.
      stateStore: new WebStorageStateStore({
        store: sessionStorage,
        prefix: 'people-gator.oidc-state.',
      }),
      staleStateAgeInSeconds: 600,
      requestTimeoutInSeconds: 10,
      revokeTokensOnSignout: true,
      revokeTokenTypes: ['refresh_token'],
    })
  }

  private async validate(user: User): Promise<void> {
    if (!user.id_token) throw new Error('Missing identity token')
    const metadata = await this.manager.metadataService.getMetadata()
    if (metadata.issuer !== this.authority || !metadata.jwks_uri)
      throw new Error('Unexpected identity provider')
    this.signingKeys ??= createRemoteJWKSet(new URL(metadata.jwks_uri), { timeoutDuration: 10000 })
    const { payload } = await jwtVerify(user.id_token, this.signingKeys, {
      issuer: this.authority,
      audience: this.clientId,
      algorithms: ['ES256', 'RS256'],
      requiredClaims: ['sub', 'iat', 'exp'],
      clockTolerance: 30,
    })
    if (payload.azp !== undefined && payload.azp !== this.clientId)
      throw new Error('Unexpected authorized party')
    if (Array.isArray(payload.aud) && payload.aud.length > 1 && payload.azp !== this.clientId)
      throw new Error('Missing authorized party')
  }

  initialize(): Promise<void> {
    this.initialized ??= this.initializeOnce()
    return this.initialized
  }

  private async initializeOnce(): Promise<void> {
    // Remove obsolete custom-provider tokens, including those from older previews.
    sessionStorage.removeItem('people-gator.access-token')
    sessionStorage.removeItem('people-gator.refresh-token')
    const params = new URLSearchParams(location.search)
    const callback =
      ['/docs', '/auth-callback.html'].includes(location.pathname) &&
      params.has('state') &&
      (params.has('code') || params.has('error'))
    if (!callback) return
    try {
      // The library checks transaction state and nonce and performs the PKCE exchange.
      const user = await this.manager.signinRedirectCallback(location.href)
      await this.validate(user)
      sessionStorage.setItem(this.hint, '1')
      sessionStorage.removeItem(this.recovering)
      history.replaceState(null, '', target(user.state))
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    } catch (error) {
      await this.manager.removeUser()
      sessionStorage.removeItem(this.hint)
      sessionStorage.removeItem(this.recovering)
      const returnTo = error instanceof ErrorResponse ? target(error.state) : '/docs'
      history.replaceState(null, '', returnTo)
      // An anonymous check must leave public docs usable and avoid redirect loops.
      if (
        error instanceof ErrorResponse &&
        [
          'login_required',
          'interaction_required',
          'account_selection_required',
          'consent_required',
        ].includes(error.error ?? '')
      )
        return
      throw new Error('Sign-in could not be completed. Try again.')
    }
  }

  accessToken(): Promise<string | undefined> {
    this.pendingToken ??= this.resolveToken().finally(() => {
      this.pendingToken = undefined
    })
    return this.pendingToken
  }

  private async resolveToken(): Promise<string | undefined> {
    await this.initialize()
    let user = await this.manager.getUser()
    if (user && (user.expires_in ?? 0) <= 30) {
      try {
        if (!user.refresh_token) throw new Error('Session requires renewal')
        const previousIdentity = user.id_token
        user = await this.manager.signinSilent()
        if (user?.id_token && user.id_token !== previousIdentity) await this.validate(user)
      } catch {
        await this.manager.removeUser()
        user = null
      }
    }
    if (user?.access_token) return user.access_token
    if (sessionStorage.getItem(this.hint) && !sessionStorage.getItem(this.recovering)) {
      await this.signIn(location.pathname + location.search + location.hash, true)
    }
    return undefined
  }

  async signIn(returnTo: string, silent = false): Promise<void> {
    if (this.navigating) return
    this.navigating = true
    if (silent) sessionStorage.setItem(this.recovering, '1')
    const path = safeReturnPath(returnTo)
    try {
      await this.manager.signinRedirect({
        state: { returnTo: path },
        nonce: crypto.randomUUID(),
        redirect_uri:
          location.origin +
          (new URL(path, location.origin).pathname === '/docs' ? '/docs' : '/auth-callback.html'),
        ...(silent ? { prompt: 'none' } : {}),
      })
    } catch {
      this.navigating = false
      sessionStorage.removeItem(this.recovering)
      throw new Error('Sign-in service unavailable. Try again.')
    }
  }

  async signOut(): Promise<void> {
    sessionStorage.removeItem(this.hint)
    sessionStorage.removeItem(this.recovering)
    await this.manager.signoutRedirect({ state: { signedOut: true } })
  }

  async finishSignOut(): Promise<void> {
    await this.manager.signoutRedirectCallback(location.href)
    history.replaceState(null, '', '/login.html')
  }
}

let configured: AuthenticationProvider | undefined
export function authenticationProvider(): AuthenticationProvider {
  configured ??= new OidcAuthenticationProvider(
    (
      import.meta.env.VITE_OIDC_AUTHORITY ||
      import.meta.env.VITE_AUTH_BASE_URL ||
      location.origin
    ).replace(/\/+$/, ''),
    import.meta.env.VITE_OIDC_CLIENT_ID || 'people-gator-browser',
    import.meta.env.VITE_OIDC_SCOPE || 'openid profile offline_access',
  )
  return configured
}
