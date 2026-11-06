import { initializeTelemetry } from './telemetry'

async function bootstrap() {
  const { getAccessToken } = await import('./query/auth')
  try {
    await getAccessToken()
  } catch {
    return
  }
  await initializeTelemetry()
  // Router and client modules may issue requests during initialization.
  await import('./mount')
}

void bootstrap()
