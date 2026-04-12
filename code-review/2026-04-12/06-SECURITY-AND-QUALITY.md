# Security and Quality — 2026-04-12

## Security Posture

### Authentication
- JWT-based auth on all protected endpoints
- Token refresh endpoint at `/auth/refresh`
- No unauthenticated paths except `/auth/register` and `/auth/login`

### Rate Limiting (verified)
- `@limiter.limit("5/hour")` on all AI-heavy endpoints:
  - `POST /search-queries/generate`
  - `POST /search-queries/evaluate`
  - `POST /search-queries/optimize`
  - `POST /profile/optimize`
- Cover letter generation: no rate limit decorator found — considered LOW risk since it requires authenticated job context

### Input Validation
- All endpoints use Pydantic schemas for request validation
- Resume text passed directly to OpenAI prompt — acceptable since it's user's own content
- No XSS risk (backend only, no HTML rendering)

### Error Handling
- `/profile/optimize` returns sanitized error messages (TD-023 resolved)
- Sentry DSN configured on Render for production error capture (OPS-01 resolved)
- React ErrorBoundary wraps the extension sidebar (TD-033 resolved)

### OpenAI Quota Protection
- `generate_embedding` calls are guarded with quota/retry protection
- Email alert to `info@servicevision.net` when quota is exhausted
- LRU cache prevents redundant embedding API calls

## Quality Observations

### Extension
- TypeScript strict: 0 errors
- No bare `console.log` in production paths (draft-saver.ts migrated this review)
- Remaining `console.error` calls are legitimate catch-block error signals
- `as any` casts limited to Nuxt state scraping (unavoidable in browser extension context)

### API
- No bare `print()` statements
- Logging via Python `logging` module throughout
- All services use `async/await` consistently

## Known Non-Issues

- `Record<string, any>` in `background/index.ts` — parsing Upwork's Nuxt state (untyped by design)
- DB integration tests fail locally (no test PostgreSQL) — they pass in CI with a real DB
- `slowapi` DeprecationWarning about `asyncio.iscoroutinefunction` — third-party library issue, not our code
