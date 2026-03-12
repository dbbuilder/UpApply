# Session Context - 2026-03-11b

**Project:** UpApply
**Path:** `/Users/admin/dev2/UpApply`

## Summary

Short session focused on verifying and fixing the `include_call_offer` flag end-to-end. The flag was correctly wired for initial cover letter generation but was silently ignored on regeneration — `CoverLetterRegenerateRequest` had no such field, so the API endpoint always used the default (`True`) regardless of what the user selected in the UI.

Fixed all layers: schema, service (`regenerate_cover_letter` now accepts and passes the flag to `build_system_prompt`), API endpoint (both the feedback-edit and fresh-regenerate branches), extension api-client, store, and Generator.tsx. The `includeCallOffer` checkbox in the UI now correctly controls all three generation paths: initial, regenerate-with-feedback, and regenerate-fresh.

## Files Modified

- `/Users/admin/dev2/UpApply/api/app/schemas/job.py` — added `include_call_offer: bool = True` to `CoverLetterRegenerateRequest`
- `/Users/admin/dev2/UpApply/api/app/services/cover_letter.py` — `regenerate_cover_letter()` accepts `include_call_offer` and passes to `build_system_prompt`
- `/Users/admin/dev2/UpApply/api/app/api/v1/jobs.py` — both regenerate code paths pass `request.include_call_offer` to service
- `/Users/admin/dev2/UpApply/extension/src/lib/api-client.ts` — `regenerateCoverLetter()` accepts `includeCallOffer`, sends as `include_call_offer` in body
- `/Users/admin/dev2/UpApply/extension/src/sidebar/store.ts` — `regenerateCoverLetter()` signature + fallback-to-generate both pass `includeCallOffer`
- `/Users/admin/dev2/UpApply/extension/src/sidebar/pages/Generator.tsx` — `handleRegenerate` passes `includeCallOffer` state

## Current State

- `include_call_offer` fully wired end-to-end for all generation paths
- `npm run type-check` passes clean
- Committed and pushed: `4ce5f59` on `main`
- API deployed on Render (auto-deploys on push)

## Next Steps

- [ ] Live-test milestone description fill on row 3 (widened selectors in previous session need verification)
- [ ] Verify client country from GraphQL `client.location.country` on live jobs with geo scoring
- [ ] Upload ChatGPT conversations.json export to import proposal memories
- [ ] Pin Docker Python version: `FROM python:3.11.11-slim` in `api/Dockerfile`
- [ ] Consider making geo tiers user-configurable via profile settings

## Open Questions / Blockers

- Milestone row 3 selector widening (from prior session) not yet live-tested — may still need adjustment
- Geo tier thresholds (+15 US, +5 EU/CA/AU, -15 low) are hardcoded in `job_analysis.py` — fine for now, but flagged for future profile setting
