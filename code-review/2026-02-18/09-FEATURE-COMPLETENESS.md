# Feature Completeness Review: UpApply

| Field | Value |
|-------|-------|
| Date | 2026-02-18 |
| Reviewer | Chris Therriault |
| Rating | YELLOW |

## Findings

### FC-001: Attachment Extraction Not Wired End-to-End in Extension

| Field | Value |
|-------|-------|
| Severity | HIGH |
| Location | `extension/src/sidebar/pages/Generator.tsx:232-320` |
| Status | Open |
| Effort | 3 SP |

**Code:**
```typescript
// We need a job ID - if we don't have one, we can't save yet
// For now, just log that we have attachments
console.log('UpApply: Downloaded', attachmentData.length, 'attachments for text extraction');
setAttachmentCount(attachmentData.length);
```

**Risk:** The attachment download and extraction pipeline is partially implemented. The backend endpoint exists (`POST /jobs/{id}/extract-attachments`), the extension downloads attachments, but the extension never sends them to the API because it doesn't have a `job_id` at that point in the flow. The extracted text is logged but not used.

**Recommendation:** Wire the full flow:
1. Create/save the job first via `POST /jobs` to get a `job_id`
2. Then call `POST /jobs/{id}/extract-attachments` with downloaded data
3. Use the enriched job data (with attachment text) for analysis and cover letter generation

---

### FC-002: Cover Letter "Regenerate" Uses Fresh Generation Instead of Feedback Loop

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | `extension/src/sidebar/pages/Generator.tsx:575-579` |
| Status | Open |
| Effort | 3 SP |

**Code:**
```typescript
<button onClick={handleGenerate}>
  Regenerate
</button>
```

**Risk:** The "Regenerate" button calls `generateCoverLetter()` which creates a completely new cover letter, ignoring the existing one. The API supports `POST /cover-letters/{id}/regenerate` with a `feedback` parameter for guided regeneration, but the extension doesn't use it.

**Recommendation:** Add a feedback input when regenerating:
- Show a text field: "What should be different?"
- Call the regenerate endpoint with the original letter ID and feedback
- This is a core differentiator -- the ability to iterate on cover letters

---

### FC-003: Application Tracking Not Connected to UI

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | `extension/src/lib/api-client.ts:249-269` |
| Status | Open |
| Effort | 5 SP |

**Risk:** The API has full application tracking (`POST /applications`, `PUT /applications/{id}/outcome`, `GET /applications/stats`) and the extension API client has methods for all of them, but there's no UI to:
- Track that a proposal was submitted
- Record outcomes (hired, declined, no response)
- View application history with outcomes

The History page exists but needs to display this data and allow outcome recording.

**Recommendation:** After filling the cover letter, prompt: "Mark this job as applied?" -> creates an application record. Add outcome tracking to the History page.

---

### FC-004: Analytics Dashboard Returns Empty Data

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | `extension/src/sidebar/pages/Analytics.tsx` |
| Status | Open |
| Effort | 3 SP |

**Risk:** The Analytics page calls `getAnalyticsDashboard()` which hits `GET /feedback/analytics/dashboard`. This endpoint generates insights but requires application data with outcomes to be meaningful. Without FC-003 being wired up, this page will always show empty/zeroed stats.

**Recommendation:** This becomes useful once application tracking (FC-003) is connected. For now, add a message: "Submit proposals and track outcomes to see analytics."

---

### FC-005: Proposal Import from Upwork Not Accessible from UI

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `extension/src/lib/api-client.ts:336-341` |
| Status | Open |
| Effort | 3 SP |

**Risk:** The API has `POST /proposals/import-from-upwork` and the content script can scrape proposals from the "My Proposals" page (`SCRAPE_PROPOSALS` message handler). The API client has `importProposalsFromUpwork()`. But there's no UI button to trigger this flow.

**Recommendation:** Add a button to the History or Analytics page: "Import Past Proposals from Upwork". Navigate to the My Proposals page, scrape, and import. This seeds the proposal memory for better cover letter generation.

---

### FC-006: Profile Wizard StepMemories Has No Memory Import UI

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `extension/src/sidebar/components/ProfileWizard/StepMemories.tsx` |
| Status | Open |
| Effort | 2 SP |

**Risk:** The setup wizard has a memories step, but the actual memory creation/import experience during setup may be thin. The API supports `POST /memories/bulk-import` and `POST /profile/import-resume` for seeding memories from a resume.

**Recommendation:** Ensure the resume import in the setup wizard triggers memory extraction and shows the user what memories were created.

---

### FC-007: No Offline/Network Failure Handling

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | `extension/src/lib/api-client.ts:44-72` |
| Status | Open |
| Effort | 3 SP |

**Risk:** If the Render API is cold-starting (30-60s on free/starter plans) or the user has no internet, every API call fails silently. The `ApiError` class exists but network errors (TypeError: Failed to fetch) aren't caught.

**Recommendation:** Add network error detection and show a "Connecting to server..." state with retry. Handle Render cold-start by showing a brief "Warming up server..." message on first 502/503.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 4 |
| LOW | 2 |
| **Total** | **7** |

The backend API is feature-complete. Most gaps are in the extension UI, where several API capabilities aren't yet wired into the user interface. The most impactful items are completing the attachment extraction pipeline (FC-001), adding the feedback-based regeneration flow (FC-002), and connecting application tracking (FC-003).
