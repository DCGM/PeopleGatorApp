import {
  connectSwaggerSession,
  type SwaggerRequest,
  type SwaggerSessionUI,
} from './query/swagger-session'

declare global {
  interface Window {
    ui?: SwaggerSessionUI
    peopleGatorDocsReady?: boolean
    peopleGatorDocsAuth?: { intercept(request: SwaggerRequest): Promise<SwaggerRequest> }
  }
}

function ready() {
  if (!window.ui) return
  const session = connectSwaggerSession(window.ui)
  window.peopleGatorDocsAuth = { intercept: session.intercept }
  document.addEventListener('click', session.signIn)
  void session.ready()
}
if (window.peopleGatorDocsReady) ready()
else window.addEventListener('peoplegator:docs-ready', ready, { once: true })
