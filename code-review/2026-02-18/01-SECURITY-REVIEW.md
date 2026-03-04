# Security Review: UpApply

| Field | Value |
|-------|-------|
| Date | 2026-02-18 |
| Reviewer | Chris Therriault |
| Rating | YELLOW |

## Findings

### SEC-001: Default Secret Key in Config

| Field | Value |
|-------|-------|
| Severity | CRITICAL |
| CWE | CWE-798 |
| Location | `api/app/core/config.py:63` |
| Status | Open |
| Effort | 0.5 SP |

**Code:**
```python
secret_key: str = "dev-secret-key-change-in-production"
```

**Risk:** If `SECRET_KEY` env var is not set in production, all JWTs are signed with a known hardcoded key. Any attacker can forge valid tokens for any user.

**Recommendation:** Fail startup if `SECRET_KEY` is not set in production. The `render.yaml` does `generateValue: true` for SECRET_KEY, so this is likely set -- but add a runtime guard:
```python
@field_validator("secret_key", mode="after")
@classmethod
def validate_secret_key(cls, v, info):
    if v == "dev-secret-key-change-in-production" and info.data.get("environment") == "production":
        raise ValueError("SECRET_KEY must be set in production")
    return v
```

---

### SEC-002: CORS Allows All Origins with No Credential Protection

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| CWE | CWE-942 |
| Location | `api/app/main.py:29-35` |
| Status | Open |
| Effort | 2 SP |

**Code:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Risk:** Any website can make API requests to the backend. While credentials=False prevents cookie-based attacks, the API uses Bearer tokens which are sent explicitly -- so this primarily means any malicious site could call the API if it steals a token from storage.

**Recommendation:** For Chrome extensions, wildcard CORS is sometimes necessary since extension IDs are dynamic. This is acceptable for beta. Before CWS submission, consider restricting to `chrome-extension://*` and the Upwork domain.

---

### SEC-003: Beta Feedback Endpoint Has No Rate Limiting

| Field | Value |
|-------|-------|
| Severity | HIGH |
| CWE | CWE-770 |
| Location | `api/app/api/v1/beta_feedback.py:21-47` |
| Status | Open |
| Effort | 2 SP |

**Code:**
```python
@router.post("", response_model=BetaFeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_beta_feedback(
    feedback_data: BetaFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
```

**Risk:** No authentication required and no rate limiting. An attacker could flood the database with feedback submissions, causing storage exhaustion on the 256MB database plan.

**Recommendation:** Add IP-based rate limiting using `slowapi` or a simple in-memory rate limiter. Limit to ~10 submissions per IP per hour.

---

### SEC-004: No Rate Limiting on Auth Endpoints

| Field | Value |
|-------|-------|
| Severity | HIGH |
| CWE | CWE-307 |
| Location | `api/app/api/v1/auth.py:71-97` |
| Status | Open |
| Effort | 3 SP |

**Risk:** Login and registration endpoints have no rate limiting, enabling brute-force password attacks and account enumeration.

**Recommendation:** Add rate limiting to `/auth/login` (5 attempts per minute per IP), `/auth/register` (3 per minute per IP). Use `slowapi` middleware.

---

### SEC-005: Beta Feedback List Endpoint Has No Authentication

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| CWE | CWE-306 |
| Location | `api/app/api/v1/beta_feedback.py:50-81` |
| Status | Open |
| Effort | 1 SP |

**Code:**
```python
@router.get("", response_model=BetaFeedbackList)
async def list_beta_feedback(
    feedback_type: Optional[str] = None,
    ...
    db: AsyncSession = Depends(get_db),
):
    """List beta feedback (for review purposes).
    In production, this should be protected or removed."""
```

**Risk:** Anyone can read all beta feedback including user emails, page URLs, and user IDs. The code even has a TODO comment about this.

**Recommendation:** Add `get_current_user` dependency with admin check, or remove the endpoint and query feedback via database directly.

---

### SEC-006: Error Messages Leak Internal Details

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| CWE | CWE-209 |
| Location | `api/app/api/v1/auth.py:64-68` |
| Status | Open |
| Effort | 1 SP |

**Code:**
```python
except Exception as e:
    logger.exception(f"Registration error: {e}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Registration failed: {str(e)}",
    )
```

**Risk:** Internal exception details (database errors, stack traces) are returned to clients.

**Recommendation:** Return generic error message to client, keep detailed logging server-side:
```python
detail="Registration failed. Please try again."
```

---

### SEC-007: JWT Token Has 7-Day Expiry with No Refresh Token Rotation

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| CWE | CWE-613 |
| Location | `api/app/core/config.py:65` |
| Status | Open |
| Effort | 5 SP |

**Code:**
```python
access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
```

**Risk:** Long-lived tokens increase the window for token theft. There's a `/auth/refresh` endpoint but it returns a new token with the same long expiry, and doesn't invalidate the old one.

**Recommendation:** For beta phase, this is acceptable. Before CWS: reduce access token to 1 hour, add proper refresh token flow with token rotation and revocation.

---

### SEC-008: Email Passed as F-String in Log Statement

| Field | Value |
|-------|-------|
| Severity | LOW |
| CWE | CWE-117 |
| Location | `api/app/api/v1/auth.py:39` |
| Status | Open |
| Effort | 0.5 SP |

**Code:**
```python
logger.info(f"Creating user with email: {user_data.email}")
```

**Risk:** User-controlled email value is interpolated into log output. Minor log injection risk.

**Recommendation:** Use structured logging: `logger.info("Creating user", extra={"email": user_data.email})`

---

### SEC-009: No Input Validation on Job Description/Cover Letter Content

| Field | Value |
|-------|-------|
| Severity | LOW |
| CWE | CWE-20 |
| Location | `api/app/schemas/job.py:21-23` |
| Status | Open |
| Effort | 1 SP |

**Risk:** No max length validation on `description`, `title`, or other text fields. A malicious client could submit extremely large payloads.

**Recommendation:** Add `max_length` validators to Pydantic schemas:
```python
title: str = Field(..., max_length=1000)
description: str = Field(..., max_length=50000)
```

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 2 |
| MEDIUM | 4 |
| LOW | 2 |
| **Total** | **9** |

The security posture is acceptable for a beta/dev environment. The CRITICAL item (SEC-001) is mitigated by Render's auto-generated SECRET_KEY but should have a runtime guard. The HIGH items (rate limiting) should be addressed before wider distribution.
