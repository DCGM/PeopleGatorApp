// Compatibility entry: app and Swagger now share one OIDC browser journey.
process.env.OIDC_APP_ORIGIN ||= process.env.SWAGGER_ORIGIN || 'http://localhost:5189'
process.env.OIDC_EVIDENCE ||= process.env.SWAGGER_EVIDENCE || '/tmp/issue89-oidc-evidence'
await import('./check-oidc-login.mjs')
