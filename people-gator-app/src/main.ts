import { initializeTelemetry } from './telemetry'

async function bootstrap() {
  await initializeTelemetry()
  const { getAccessToken } = await import('./query/auth')
  try { await getAccessToken() } catch { return }
  // Router and client modules may issue requests during initialization.
  await import('./mount')
}

void bootstrap()
