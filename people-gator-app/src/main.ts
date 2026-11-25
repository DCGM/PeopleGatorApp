import { loadAppConfig } from './app-config'
import { initializeTelemetry } from './telemetry'

async function bootstrap() {
  await Promise.all([initializeTelemetry(), loadAppConfig()])
  // Router and client modules may issue requests during initialization.
  await import('./mount')
}

void bootstrap()
