# Appendix B: Dependency Audit

| Field | Value |
|-------|-------|
| Date | 2026-02-18 |

## Extension (npm)

### npm audit output

```
# npm audit report

ajv  <8.18.0
Severity: moderate
ajv has ReDoS when using `$data` option
No fix available
node_modules/ajv
  @eslint/eslintrc  *
    eslint  >=4.2.0
      @eslint-community/eslint-utils  *
      eslint-plugin-react-refresh  *

esbuild  <=0.24.2
Severity: moderate
esbuild enables any website to send any requests to the development server
fix available via `npm audit fix --force` (breaking: vite@7.3.1)
node_modules/esbuild
  vite  0.11.0 - 6.1.6

7 moderate severity vulnerabilities
```

### Assessment

| Vulnerability | Severity | Impact | Action |
|--------------|----------|--------|--------|
| ajv ReDoS | Moderate | Dev-only (eslint). Not in production bundle. | No action needed. |
| esbuild dev server | Moderate | Dev-only. Not in production bundle. | No action needed. Fix requires vite 7 upgrade (breaking). |

**Verdict:** All 7 vulnerabilities are in dev dependencies only. They do not affect the production Chrome extension bundle. No immediate action required.

## API (Python)

### Dependencies

| Package | Version Spec | Notes |
|---------|-------------|-------|
| fastapi | >=0.109.0 | Web framework |
| uvicorn[standard] | >=0.27.0 | ASGI server |
| pydantic | >=2.5.0 | Validation |
| pydantic-settings | >=2.1.0 | Config management |
| sqlalchemy | >=2.0.25 | ORM |
| asyncpg | >=0.29.0 | PostgreSQL driver |
| alembic | >=1.13.0 | Migrations |
| openai | >=1.10.0 | AI API |
| httpx | >=0.26.0 | HTTP client |
| python-multipart | >=0.0.6 | File uploads |
| python-jose[cryptography] | >=3.3.0 | JWT handling |
| pgvector | >=0.2.4 | Vector similarity |
| tenacity | >=8.2.3 | Retry logic |
| email-validator | >=2.1.0 | Email validation |
| bcrypt | >=4.1.0 | Password hashing |
| pdfplumber | >=0.10.0 | PDF text extraction |
| python-docx | >=1.0.0 | DOCX text extraction |

### Assessment

| Concern | Severity | Notes |
|---------|----------|-------|
| python-jose maintenance | LOW | python-jose has limited maintenance. Consider migrating to `PyJWT` or `authlib` eventually. |
| Version pinning | LOW | Using `>=` for all dependencies. Consider pinning major versions to prevent breaking upgrades. |

**Verdict:** No known vulnerabilities in production dependencies. The dependency set is lean and appropriate for the use case.
