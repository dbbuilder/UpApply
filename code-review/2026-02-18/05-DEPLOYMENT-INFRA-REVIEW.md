# Deployment & Infrastructure Review: UpApply

| Field | Value |
|-------|-------|
| Date | 2026-02-18 |
| Reviewer | Chris Therriault |
| Rating | YELLOW |

## Findings

### INFRA-001: No Database Backup Strategy

| Field | Value |
|-------|-------|
| Severity | HIGH |
| Location | `render.yaml` |
| Status | Open |
| Effort | 2 SP |

**Risk:** The Render basic-256mb PostgreSQL plan has limited backup options. If the database is corrupted or data is lost, there may be no recovery path.

**Recommendation:** Render Starter databases include automatic daily backups. Verify this is enabled in the Render dashboard. For additional safety, set up a cron job or GitHub Action that runs `pg_dump` weekly and stores the backup in a cloud bucket.

---

### INFRA-002: No Monitoring or Alerting

| Field | Value |
|-------|-------|
| Severity | HIGH |
| Location | N/A |
| Status | Open |
| Effort | 3 SP |

**Risk:** No application monitoring, error tracking, or alerting. If the API crashes, OpenAI calls fail, or the database fills up, no one is notified. The health check endpoint exists but only checks database connectivity.

**Recommendation:** Add Sentry for error tracking (project DSN already planned in credentials.md but not yet created). Add uptime monitoring via Render's built-in or a free service like UptimeRobot. Consider logging OpenAI API errors and costs.

---

### INFRA-003: No Environment Separation

| Field | Value |
|-------|-------|
| Severity | MEDIUM |
| Location | `api/app/core/config.py:20`, `render.yaml` |
| Status | Open |
| Effort | 5 SP |

**Risk:** There's a single deployment environment. The `environment` config defaults to "development" and `is_production` property exists but isn't used anywhere. Development, testing, and production all hit the same database.

**Recommendation:** For beta, single environment is fine. Before CWS launch, add a staging environment on Render with a separate database. Use environment-specific configs (debug logging in dev, structured logging in prod, etc.).

---

### INFRA-004: Dockerfile Uses Python 3.11 But pyproject.toml Requires >=3.11

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `api/Dockerfile:1` |
| Status | Open |
| Effort | 0.5 SP |

**Code:**
```dockerfile
FROM python:3.11-slim
```

**Risk:** Local development uses Python 3.14 (per venv path), but Docker uses 3.11. This could cause issues if code uses 3.12+ features.

**Recommendation:** Pin to a specific patch version like `python:3.11.11-slim` for reproducibility. Or upgrade to 3.12 to match modern Python features.

---

### INFRA-005: start.sh Does DATABASE_URL Transform That Config.py Also Does

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `api/start.sh:4-9`, `api/app/core/config.py:29-39` |
| Status | Open |
| Effort | 0.5 SP |

**Risk:** The `postgres://` to `postgresql+asyncpg://` transform is done in both `start.sh` (for Alembic) and `config.py` (for SQLAlchemy). While not harmful, it's duplicated logic.

**Recommendation:** Remove the transform from `start.sh` and configure Alembic's `env.py` to use the same Settings transform. Or keep both -- it's defensive and harmless.

---

### INFRA-006: Extension Version Not Auto-Incremented

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `extension/public/manifest.json:4`, `extension/package.json:3` |
| Status | Open |
| Effort | 1 SP |

**Risk:** Both `manifest.json` and `package.json` hardcode version `1.0.0`. As updates are distributed to testers, version tracking is manual.

**Recommendation:** Use a build script that increments the version from `package.json` into `manifest.json` at build time. Or use a date-based version like `2026.2.18`.

---

### INFRA-007: Docker Health Check Curls Localhost But Render May Use Different Port

| Field | Value |
|-------|-------|
| Severity | LOW |
| Location | `api/Dockerfile:29-30` |
| Status | Open |
| Effort | 0.5 SP |

**Code:**
```dockerfile
HEALTHCHECK ... CMD curl -f http://localhost:8000/health || exit 1
```

**Risk:** The CMD in `start.sh` uses `${PORT:-8000}`. If Render sets PORT to something other than 8000, the Docker HEALTHCHECK will fail.

**Recommendation:** Use `${PORT:-8000}` in the HEALTHCHECK too, or remove the Docker HEALTHCHECK since Render has its own `healthCheckPath: /health` configured.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 2 |
| MEDIUM | 1 |
| LOW | 4 |
| **Total** | **7** |

Deployment is functional and auto-deploys work. The main gaps are monitoring/alerting and backup verification. These become increasingly important as real user data accumulates.
