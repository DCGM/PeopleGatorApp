// Compatibility entry for the standard provider-independent OIDC journey.
process.env.OIDC_APP_ORIGIN ||= process.env.AUTH_GATEWAY_ORIGIN || 'http://localhost:5189'
process.env.OIDC_EVIDENCE ||= process.env.AUTH_GATEWAY_EVIDENCE || '/tmp/issue89-oidc-evidence'
await import('./check-oidc-login.mjs')
