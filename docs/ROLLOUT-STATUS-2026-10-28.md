# UpApply memory-driven generation: where we stand and how to finish

Status as of 2026-10-28. Covers the v2 cover-letter engine, the ServiceVision voice kit and the blind A/B rollout.

## 1. Where we stand

**The new engine passed and is live for Chris.** Round 5 of the blind A/B test scored 17 of 20 (85%) with no unsupported claims, clearing the 75% bar. `generation_v2` was switched on for chris@servicevision.net on 2026-10-28. Chris is the only user on it. Every letter and screening answer he generates now comes from the new engine.

**A three-way follow-up on the round-5 non-wins** (current generator vs round-5 letter vs a letter with the round-5 notes applied) went 2 of 3 to the new engine. Counting both tests, Chris preferred a new-engine letter for 19 of the 20 jobs. The one current-generator win carried two faults the kit already bans: copied file names from the post, and no NDA offer.

### What is live

| Piece | State |
|---|---|
| API on Render | Deploy `ad0c7dc` (PR #32) live, `/health` 200 |
| `generation_v2` | On for Chris only; everyone else on the legacy pipeline |
| Voice kit | v0.5.0 (`dbbuilder-org/sv-writing-style`), vendored into `api/app/voice/chris.json` |
| Writer | `claude-opus-5-5` via the AICostCentral proxy, effort high |
| Job scoring / small calls | `gpt-5.4-nano` (gpt-4.1-nano was retired; Doppler and Render updated) |
| Facts | ~265+ approved facts; brief `domain` phrase pulls on-domain products (FireProofApp, SchoolVision) into evidence |
| Checks in `verify.py` | De-AI bans (dashes, emojis, tell-words), company name, short opening, close ends on the call offer, NDA as a clause ("would be willing to sign an NDA in advance"), no tech in the close, no live-or-die wording, one "happy" per close, claim check with per-claim verdicts |

### How we got here

| Round | New engine preferred | What changed after it |
|---|---|---|
| 1 (2026-10-20) | 4/20 | Round found asymmetric; exclusions made symmetric |
| 2 (2026-10-23) | 13/20 (65%) | Voice kit created; claim checker narrowed to the draft |
| 3 (2026-10-23) | 11/20 (55%) | De-AI checks, NDA, company name, close rules; domain evidence |
| 4 (2026-10-28) | 11/20 (55%) | Openings cut to 1-2 sentences; NDA wording; no tech in the close |
| 5 (2026-10-28) | **17/20 (85%), passed** | Flag switched on; v0.5.0 notes folded in |
| A/B/C follow-up | 2/3 of the round-5 non-wins | No new rule needed |

Lesson worth keeping: 20 AI judges given the kit predicted round 4 at 20/20; Chris gave it 11/20. Only Chris's own blind judgement counts.

### Loose ends in this checkout

- The local checkout is on `feat/round-3-voice` (stale; `origin/main` is at `ad0c7dc`). Chris's uncommitted extension version bump (1.0.19) lives here, so switch branches only after deciding Q9.
- `docs/NEXT.md` on this branch still describes round 4 as pending and needs a refresh once these decisions are made.
- OrbStack (Docker) was hung on 2026-10-24, so database tests have been running in CI only.

## Update, later on 2026-10-28

- **Proxy timeouts (Q11): root cause found.** AICostCentral's `/v1/messages` route had `maxDuration = 60`. Measured through it: a non-streaming writer call failed with 504 at 60.4s, and streaming calls that ran longer were cut at 60.3s and 60.5s. Streaming does not help, so UpApply #34 was closed. Fix: dbbuilder-org/AI-Cost-Central#27 raises it to 300s. **Not merged or deployed (your call).** Until it ships, any call over about 60 seconds fails; the screening-answers path measured 56s.
- **Merged:** #33 (call-offer wording check, Q6 A; skipped when the client asks for no calls) and #35 (an outcome credits the letter you submitted, not a newer unsent draft).
- **Facts (Q1):** 20 "Vision Companies" rewrites are waiting for you at https://claude.ai/artifact/RDAcqoVNqPb8d1d4jwszaL. Nothing changes until you approve.
- **Live smoke test on main (rolled back):** screening answers 56s, letter 38s, refine 27s, no rule warnings, v0.5 NDA wording in the close.
- **Docker is working again;** the test database container was recreated and the full suite (769 tests) passes locally.

## 2. What "fruition" means

1. The new engine is the only pipeline, and the legacy code is removed.
2. Letters keep passing Chris's eye in daily use, not just in a test packet.
3. The learning loop works: outcomes (reply, interview, hire) come back from Upwork and strengthen the facts that won.
4. It runs without babysitting: no proxy timeouts in real use, clean facts, docs that match the code.

## 3. The path

### Phase 1: live use (now to ~2026-11-04)

- [ ] Use the new engine on real jobs for a week. Note any letter he has to rewrite and why; each note goes into the kit's feedback log (that loop produced every rule so far).
- [ ] Check that the refine chat and the screening-answer endpoint behave on real posts (both run the same checks).
- [ ] **Facts: "the Vision Companies".** Rewrite the approved facts that say "global SaaS company" or pair SchoolVision with scale, so letters say "the Vision Companies" (SchoolVision = edtech, FranchiseVision = retail). Claude drafts the rewrites; Chris approves each one (Q1).
- [ ] **Proxy timeouts (Q11).** The eval hit repeated 504s from the AI proxy on long Opus writer calls. In live use that would be a failed generation. Decide the fix before relying on it daily.

### Phase 2: close the learning loop (~2026-11-04 to 11-11)

- [ ] Re-run the Proposals import in the extension so outcomes come in as readable status text, not Upwork's numeric codes (only "7 = active submitted" is known today).
- [ ] Confirm outcome sync credits facts once per proposal (`proposals.facts_credited_at`) and that winning facts rise in evidence ranking.
- [ ] Decide how to capture client feedback as facts (Q5): it is the strongest evidence type and there is none yet.

### Phase 3: retire the legacy pipeline (~2026-11-11, after two weeks on v2)

- [ ] Runbook §8: remove the legacy generation path and corpus-memory retrieval, keeping the rollback statement until the removal PR ships (Q2).
- [ ] Update CLAUDE.md and the runbook to describe one pipeline.

### Phase 4: beyond Chris (optional)

- [ ] Decide whether other users get the new engine (they would get the built-in prompt, not Chris's voice) (Q3).
- [ ] Decide whether other ServiceVision writers get a voice kit, and which projects consume it next (gtm-bible, operations manual, magic-marketing) (Q13).

### Housekeeping (any time)

- [ ] Rotate the UpApply password exposed in commit 3b7affc and a session transcript; revoke the dead Render key in git history (Q12).
- [ ] Restart OrbStack when nothing else depends on it, so DB tests run locally again.
- [ ] Refresh `docs/NEXT.md` from this document.

## 4. Questions and decisions

Each has options and a recommendation. Answer by number.

**Q1. "The Vision Companies" in the facts.** Several approved facts say "global SaaS company" or put SchoolVision beside scale claims, so letters keep that wording.
- A: Claude drafts every rewrite on a review page; you approve or edit each. *(recommended)* 
- B: Change only the voice kit and let letters mix both names.
- ANSWER: A

**Q2. When to remove the legacy pipeline.**
- A: On ~2026-11-11 as the runbook says, if the two weeks go cleanly. *(recommended)*
- B: Keep it longer as a fallback (it costs nothing while the flag is per user).
- 
- ANSWER: describe what we lose in the legacy pipeline 

**Q3. Other users.** The flag is on for you only. Others would get the new engine with the built-in prompt (no voice kit).
- A: Keep it you-only until Phase 3. *(recommended)*
- B: Turn it on for all users now.
- C: Turn it on per user as each gets a voice kit.
- A: Me only for now; Gus Tello next week

**Q4. How do we judge success in real use?** Blind tests measure taste, not results.
- A: Reply/interview rate on new-engine proposals vs the prior 90 days, once outcomes import cleanly. *(recommended)*
- B: Your judgement alone (letters you send without rewriting).
- ANSWER: A + B

**Q5. Client feedback as facts.**

- A: Scrape feedback text from won-contract pages in the extension.
- B: Paste testimonials in as facts by hand. *(recommended to start: quick, and you choose the best ones)*
- ANSWER: Scrape comments from feedback by clients posted on Upwork

**Q6. Wrong or missing call-offer wording as its own check?** Today a reworded offer only trips the "nothing after the offer" check.
- A: Add a check when the call offer is requested. *(recommended)*
- B: Leave it.
- ANSWER: A

**Q7. Unused fact candidates** (about 2,700 lower-value or doubtful candidates never reach a letter).
- A: Keep them. *(recommended until Phase 2: harmless and possibly useful)*
- B: Bulk-reject to tidy the review queue.
- ANSWER: KEEP

**Q8. Doppler vs Render as source of truth.** The sync script pushes every Doppler value; the two drifted once.
- A: Doppler is authoritative; fix it first, then sync everything. *(recommended)*
- B: Sync only named keys.
- ANSWER: A

**Q9. Your extension version bump** (1.0.19, uncommitted for weeks in this checkout).
- A: Commit it on its own small PR so the checkout can follow `main`. *(recommended)*
- B: Keep it local.
- 
- ANSWER: A

**Q10. Openers that lead with experience.** Round 3 praised "Twenty-five years of .NET and SQL Server work leaves a recognizable fingerprint"; round 2 called a similar opener one to avoid. The kit reads this as "experience is fine as an insight about the work, never a résumé line."
- Confirm or correct.
- 
- Round 3 is right - but round 2 didnt like the paragraph as a whole

**Q11. Proxy timeouts on long writer calls.** The eval saw repeated 504s from the AI proxy on Opus calls at high effort.
- A: Send the writer call straight to Anthropic, keeping the proxy for the rest. *(recommended if the proxy has a hard timeout)*
- B: Lower the writer's effort to medium (faster, possibly weaker letters; would need a quick check).
- C: Add retries in the API and accept slower failures.
- ANSWER A and C

**Q12. Credentials.** Rotate the exposed password and revoke the old Render key (your action; Claude can walk through it).

**Q13. Next voice-kit consumer.** UpApply is the only one wired in.
- A: gtm-bible sales agent next (same register, biggest payoff).
- B: Operations manual or marketing next.
- C: Not yet.
- ANSWER: A and then B-marketing

## 5. Rollback

```sql
UPDATE user_profiles SET generation_v2 = false
 WHERE user_id = (SELECT id FROM users WHERE email = 'chris@servicevision.net');
```

The legacy path is untouched until Phase 3. The runbook (`docs/superpowers/runbook-memory-driven-generation.md` §5) covers opening the production database to this Mac temporarily and closing it afterwards.

## 6. Where things live

- Runbook: `docs/superpowers/runbook-memory-driven-generation.md`
- Design and plan: `docs/superpowers/specs/2026-10-12-memory-driven-generation-design.md`, `docs/superpowers/plans/2026-10-12-memory-driven-generation.md`
- A/B packets and scores: `docs/evals/<date>[-rN]/` (gitignored; `key.json` is the answer key)
- Voice kit: `~/dev2/sv/writing-style` (feedback log `chris/feedback-log.md`, rules `chris/rules.yaml`, checker `tools/check.py`)
- Skills: `sv-writing-style` and `de-ai` (linked from the kit into `~/.claude/skills`)

## 7. Decisions taken (2026-10-29)

| # | Answer | Status |
|---|---|---|
| Q1 | A: draft each rewrite, Chris approves | **Done.** 20 facts updated (15 as drafted, 5 in Chris's wording), each re-embedded; old wording backed up |
| Q2 | Describe what the legacy pipeline still gives us | Answered below |
| Q3 | Chris only; Gus Tello next week | Gus needs approved facts (and optionally a voice kit) before his flag goes on |
| Q4 | A + B: reply/interview rate vs the prior 90 days, plus Chris's own judgement | Needs the Proposals import re-run so outcomes arrive as readable statuses |
| Q5 | Scrape client feedback comments posted on Upwork | Build in the extension; needs one saved feedback page to map the DOM |
| Q6 | A: call-offer wording check | **Done** (#33; skipped when the client asks for no calls) |
| Q7 | Keep the unused candidates | No action |
| Q8 | A: Doppler authoritative, then sync | **Done.** Four Render-only keys copied into Doppler, full sync run; Render now mirrors Doppler (`DATABASE_URL` stays Render-managed; `CORS_ORIGINS` is unused by the code) |
| Q9 | A: commit the extension bump | **Done** (#36, 1.0.19); the working checkout now follows `main` |
| Q10 | Round 3 is right; round 2 disliked the paragraph as a whole | **Done** (kit v0.5.1) |
| Q11 | A + C | **Root cause fixed:** AICostCentral `/v1/messages` `maxDuration` 60 → 300 (AI-Cost-Central#27, deployed; 97s and 113s calls now complete). **C done** (#37: one retry). **A ready** (#37: `WRITER_ANTHROPIC_API_KEY`), needs a real `sk-ant-` key in Doppler `prd` to take effect |
| Q12 | Credentials | Chris's action (steps in the reply) |
| Q13 | A then B-marketing: gtm-bible sales agent, then marketing | Next build after the job-queue port |

### What the legacy pipeline still gives us (Q2)

1. **Every other user.** The flag is on for Chris only, so everyone else (Gus included, until next week) writes through the legacy pipeline. Removing it before they move would leave them without letters.
2. **Letters without facts.** Legacy writes from profile, curated memories and past proposals. v2 needs approved facts; a user with none gets a letter with no verified specifics and a warning.
3. **Job-queue auto-drafts.** `api/app/api/v1/job_queue.py` drafts queued jobs with the legacy generator even when `generation_v2` is on. These must move to v2 first.
4. **The Regenerate button.** Used only when v2 is off (v2 letters use the refine chat), so it goes with the legacy path.
5. **Per-job-type credential routing** (`proposal_anchors` cto/saas/sql/cloud/ai/fullstack). v2 uses only `always_include`; facts and the domain search do this job now.
6. **Cost and speed.** Legacy uses Sonnet 4.6 in one pass; v2 uses Opus 5.5 plus a brief, a claim check and up to one repair, so it is slower and costs more per letter.

So: remove legacy only after (a) job-queue drafts run on v2, (b) every active user is on v2 with facts loaded, and (c) the two weeks of live use go cleanly.
