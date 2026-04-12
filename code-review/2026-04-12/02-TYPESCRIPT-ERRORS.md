# TypeScript Errors — 2026-04-12

## Baseline

```
npm run type-check
> tsc --noEmit
(no output — clean)
```

**Result: 0 errors, 0 warnings.**

TypeScript is clean. No fixes required.

## Remaining `as any` Uses

All remaining `as any` casts in `background/index.ts` are legitimate:

- `window as any` — accessing `__NUXT__` which is injected by Nuxt at runtime, not typed
- `Record<string, any>` — parsing Upwork's dynamic proposal API response structure

These are acceptable given the DOM/browser extension context and Upwork's untyped Nuxt state.
No action needed.
