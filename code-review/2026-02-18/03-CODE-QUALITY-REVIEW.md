# Code Quality Review: UpApply

| Field | Value |
|-------|-------|
| Date | 2026-02-18 |
| Reviewer | Chris Therriault |
| Rating | YELLOW |

## Findings

### CQ-001: datetime.utcnow() is Deprecated

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | `api/app/api/v1/jobs.py:226`, `api/app/api/v1/jobs.py:472` |
| Status | Open |
| Effort | 1 SP |

**Code:**
```python
scraped_at=datetime.utcnow(),
```

**Risk:** `datetime.utcnow()` is deprecated in Python 3.12+ and returns a naive datetime. The column is defined with `timezone=True`, creating a mismatch.

**Recommendation:** Replace with `datetime.now(timezone.utc)` throughout.

---

### CQ-002: Bare except Clauses

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `api/app/api/v1/proposals.py:394` |
| Status | Open |
| Effort | 0.5 SP |

**Code:**
```python
try:
    submitted_at = datetime.fromisoformat(submitted_at_str.replace("Z", "+00:00"))
except:
    pass
```

**Risk:** Bare `except:` catches `SystemExit`, `KeyboardInterrupt`, etc. Should be `except (ValueError, TypeError):`.

**Recommendation:** Narrow the exception handler.

---

### CQ-003: Inconsistent Error Handling Between Endpoints

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | Various API endpoints |
| Status | Open |
| Effort | 3 SP |

**Risk:** Some endpoints wrap all logic in try/except (auth.py register), while most let exceptions propagate naturally. The `register` endpoint catches all exceptions and returns them as 500 with internal details. Other endpoints rely on FastAPI's default error handling. This inconsistency makes debugging harder.

**Recommendation:** Remove the blanket try/except from `register`. Let FastAPI handle unexpected errors with its default 500 handler. Only catch expected errors (duplicate email -> 400).

---

### CQ-004: No Type Annotations on Some Service Function Returns

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `api/app/services/job_analysis.py:320-334` |
| Status | Open |
| Effort | 0.5 SP |

**Code:**
```python
def generate_recommendation(
    match_score: float, deal_breakers: List[str], concerns: List[str]
) -> str:
```

**Risk:** Most functions are typed, which is good. A few helper functions in the service layer are missing explicit return type annotations.

**Recommendation:** Low priority. The existing type coverage is good. Add annotations as you touch these functions.

---

### CQ-005: Console.log Statements Left in Extension Code

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `extension/src/content/index.ts:97-98, 110-114, 311, 387, 398-399` |
| Status | Open |
| Effort | 1 SP |

**Risk:** Extensive `console.log` statements throughout the content script and background worker. These are useful for debugging but create noise in the browser console for end users.

**Recommendation:** Wrap in a debug flag or use a logger utility:
```typescript
const DEBUG = import.meta.env.DEV;
const log = (...args: unknown[]) => DEBUG && console.log('UpApply:', ...args);
```

---

### CQ-006: Large Function Handlers in Generator.tsx

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | `extension/src/sidebar/pages/Generator.tsx` (657 lines) |
| Status | Open |
| Effort | 5 SP |

**Risk:** The Generator page is a 657-line single component with inline state management, API calls, popup window logic, and rendering. This is the most complex component and the hardest to maintain.

**Recommendation:** Extract into sub-components:
- `<JobInfoCard />` - job details display
- `<MatchAnalysis />` - analysis results
- `<CoverLetterPanel />` - cover letter display, edit, copy, fill
- `<ScreeningQuestions />` - question/answer handling
- Move `handleFetchFullJob` to a custom hook

---

### CQ-007: Unused Import: `delete` from SQLAlchemy

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `api/app/api/v1/memories.py:5` |
| Status | Open |
| Effort | 0.5 SP |

**Code:**
```python
from sqlalchemy import select, delete
```

**Risk:** `delete` is imported but never used. The endpoint uses `db.delete(memory)` instead of a bulk delete query.

**Recommendation:** Remove unused import.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 3 |
| LOW | 4 |
| **Total** | **7** |

Code quality is solid overall. Python code follows consistent patterns and the FastAPI structure is well-organized. The extension TypeScript is functional but the Generator page needs decomposition. Main areas for improvement are consistency in error handling and cleaning up debug logging.
