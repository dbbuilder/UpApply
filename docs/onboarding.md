# UpApply — Getting Started

UpApply is a Chrome extension + AI backend that scores Upwork jobs against your profile and generates personalized cover letters in seconds.

---

## 1. Install the Extension

### Development / Beta Build

1. Clone the repo and build:
   ```bash
   cd extension
   npm install
   npm run build
   ```
2. Open `chrome://extensions` in Chrome.
3. Enable **Developer mode** (toggle, top-right).
4. Click **Load unpacked** and select the `extension/dist/` folder.
5. The UpApply icon appears in your toolbar. Pin it for easy access.

### Updating

Re-run `npm run build`, then click the refresh icon on the extension card in `chrome://extensions`.

---

## 2. Create Your Account

1. Click the UpApply icon on any Upwork page to open the sidebar.
2. Go to **Settings → Account** and register with your email + password.
3. After registering, log in — your JWT token is stored locally.

---

## 3. Complete Your Profile

Your profile is the engine behind scoring and cover letter generation. The more detail you add, the better the results.

Navigate to **Settings → Edit Profile** and fill in:

| Section | What to fill in |
|---------|----------------|
| **Identity** | Full name, professional title, bio, preferred sign-off |
| **Goals** | Career goals, ideal project, skills to highlight/develop |
| **Preferences** | Project types, industries, client types, preferred client locations |
| **Deal Breakers** | Keywords/industries to avoid, minimum budget/rate, red-flag patterns |
| **Pricing** | Hourly range, fixed-price minimum, hours/week available |

**Tip — Preferred Client Locations:** Add countries that should boost a job's score (e.g. "United States", "Canada"). Leave blank to use the built-in US/Tier-2/Low tiers.

---

## 4. Import Your Upwork History

Go to **Imports** tab and run these in order:

1. **Proposals** — scrapes your last 150 active + archived proposals with cover letters. Takes 2–5 min. Must be run on the Upwork proposals page (`/nx/proposals/`).
2. **Won Contracts** — imports your full contract history. Navigates your active Upwork tab to `/nx/contracts/`.
3. **Backfill was_hired** — run this immediately after importing proposals. Sets hired/declined status on proposals already in the corpus.
4. **Saved Jobs** — imports bookmarked jobs (last 14 days) into your Queue for scoring.
5. **Saved Searches** — imports your Upwork saved search filters as re-runnable Search Queries.

---

## 5. Score Jobs

### On Upwork search results / notifications

- Score badges (**0–100**) appear automatically on job tiles as you browse.
- **Green** ≥ 70 · **Yellow** 50–69 · **Red** < 50
- Keyword chips (MVP, AI, CTO…) appear below the badge when detected.

### From the sidebar

1. Open a job posting on Upwork — the sidebar auto-loads that job.
2. Click **Analyze** to score the job and see skill match, concerns, and deal-breaker warnings.
3. Click **Generate** to create a cover letter.

---

## 6. Generate a Cover Letter

1. With a job loaded in the sidebar, click **Generate Cover Letter**.
2. The AI uses your profile, past winning proposals, and bio memories to write a personalized letter.
3. Toggle **Include call offer** to add/remove the free-call sentence before the close.
4. Click **Insert** to paste the letter directly into the Upwork proposal text box.

---

## 7. Track Applications

After submitting a proposal on Upwork, UpApply records it automatically. View outcomes in the **History** tab.

---

## 8. Search Lab (Power Users)

Use the **Search Lab** tab to:
- Build and evaluate boolean search queries against your profile.
- Score historical jobs to see which queries surface the best matches.
- Optimize under-performing queries with AI suggestions.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Sidebar doesn't open | Refresh the Upwork page; extension only activates on `www.upwork.com` |
| Score badges not appearing | Check that you're logged in — badges require a valid API token |
| Cover letter generation fails | Ensure your profile has at least a bio and a few skills filled in |
| Import stuck on "Scraping" | The Upwork tab must stay in the foreground during proposal scraping |
| API connection error | The backend may be cold-starting on Render — wait 30s and retry |

---

## API Backend (Self-Hosted)

If you're running your own backend:

1. Copy `.env.example` → `.env` in `api/` and fill in `DATABASE_URL` and `OPENAI_API_KEY`.
2. Run migrations: `alembic upgrade head`
3. Start: `uvicorn app.main:app --reload --port 8000`
4. Set `VITE_API_URL=http://localhost:8000` in `extension/.env` and rebuild.
