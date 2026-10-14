# People Gator browser app

Vue 3/TypeScript application for scan and people search, registered documents,
person identity editing and evidence review. Vite builds the app; Vue Router,
TanStack Vue Query, Tailwind CSS 4 and shadcn-vue/Reka UI provide its screen,
server-state and interaction layers.

## Development

Use Node `^22.18.0 || >=24.12.0` (CI uses Node 24), then from this directory:

```sh
npm ci --prefer-offline --no-audit --no-fund
```

Start the API/database following [Development](../docs/DEVELOPMENT.md) and set
`.env.local` as shown there. `VITE_API_BASE_URL=http://localhost:8000` is required
for the native local workflow; without it the client falls back to a remote
development server. The app automatically logs in as the configured demo user
(`test` / `test` by default). Browser `VITE_*` values are public build inputs,
not a secure way to distribute production account credentials.

```sh
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
npm run build
npm run test:unit -- --run
```

`build` performs type checking and compilation. `npm run type-check` and
`npm run build-only` run those checks separately. Lint and formatting commands
auto-write files; inspect their changes before committing.

## Code map

- `src/router/` and `src/views/`: scan search, document list, people search,
  person details and page workspace.
- `src/query/`: generated-client integration, auth, cache keys and mutations.
- `src/viewmodels/`: filter/URL state, assignment and screen presentation logic.
- `src/components/custom/`, `src/components/ui/`: screen components and shared
  shadcn-vue primitives.
- `src/client/`: generated OpenAPI SDK; regenerate from the local API schema
  using [these instructions](../docs/DEVELOPMENT.md#updating-the-api-client).
- `src/__tests__/`: Vitest query, viewmodel and component checks.

Read [Architecture](../docs/ARCHITECTURE.md),
[Search filters](../docs/SEARCH_FILTERS.md), [Contributing](../CONTRIBUTING.md) and
[AGENTS.md](../AGENTS.md) before changes. Production Docker builds require
`--build-arg VITE_API_BASE_URL=/` for a same-origin reverse proxy; see
[Deployment](../docs/DEPLOYMENT.md).
