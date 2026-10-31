import { initializeTelemetry } from './telemetry'

async function bootstrap() {
  await initializeTelemetry()
  // Router and client modules may issue requests during initialization.
  await import('./mount')
}

void bootstrap()
