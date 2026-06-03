# PRD Appendix: Complete API Endpoint Inventory

**Generated**: 2026-06-02
**Source**: Automated audit of `/src/dashboard/routes/`
**Total Endpoints**: 253 across 25 route files

---

## Coverage Summary

| Status | Count | Description |
|--------|-------|-------------|
| **COVERED** | 9 | Explicitly documented in PRD |
| **PARTIAL** | 170+ | Related requirement exists |
| **MISSING** | 74+ | No PRD requirement found |

---

## 1. Summary Management (`summaries.py`) - 37 endpoints

### Core Summary Operations
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/summaries` | ADR-005 | COVERED |
| GET | `/guilds/{guild_id}/summaries/{summary_id}` | ADR-005 | COVERED |
| POST | `/guilds/{guild_id}/summaries/generate` | ADR-005 | COVERED |
| POST | `/guilds/{guild_id}/summaries/{summary_id}/push` | ADR-005 | COVERED |
| DELETE | `/guilds/{guild_id}/summaries/{summary_id}` | ADR-005 | PARTIAL |

### Stored Summary Operations
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/stored-summaries` | ADR-005 | PARTIAL |
| GET | `/guilds/{guild_id}/stored-summaries/{id}` | ADR-005 | PARTIAL |
| GET | `/guilds/{guild_id}/stored-summaries/{id}/next` | ADR-005 | MISSING |
| GET | `/guilds/{guild_id}/stored-summaries/{id}/prev` | ADR-005 | MISSING |
| PATCH | `/guilds/{guild_id}/stored-summaries/{id}` | ADR-005 | PARTIAL |
| DELETE | `/guilds/{guild_id}/stored-summaries/{id}` | ADR-005 | PARTIAL |
| GET | `/guilds/{guild_id}/stored-summaries/search` | ADR-005 | PARTIAL |
| GET | `/guilds/{guild_id}/stored-summaries/by-participant` | ADR-005 | PARTIAL |
| GET | `/guilds/{guild_id}/stored-summaries/calendar/{year}/{month}` | - | MISSING |
| POST | `/guilds/{guild_id}/stored-summaries/bulk-delete` | ADR-005 | PARTIAL |
| POST | `/guilds/{guild_id}/stored-summaries/bulk-regenerate` | ADR-005 | PARTIAL |

### Push/Delivery Operations
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| POST | `/guilds/{guild_id}/stored-summaries/{id}/push` | ADR-005 | PARTIAL |
| POST | `/guilds/{guild_id}/stored-summaries/{id}/push-dm` | ADR-047 | MISSING |
| POST | `/guilds/{guild_id}/stored-summaries/{id}/email` | ADR-030 | PARTIAL |

### Confluence Operations
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| POST | `/guilds/{guild_id}/stored-summaries/{id}/publish-confluence` | ADR-099 | PARTIAL |
| POST | `/guilds/{guild_id}/stored-summaries/{id}/unpublish-confluence` | ADR-099 | MISSING |
| POST | `/guilds/{guild_id}/stored-summaries/bulk-confluence-publish` | ADR-099 | PARTIAL |
| POST | `/guilds/{guild_id}/stored-summaries/bulk-confluence-unpublish` | ADR-099 | MISSING |
| GET | `/guilds/{guild_id}/settings/confluence` | ADR-099 | PARTIAL |
| PUT | `/guilds/{guild_id}/settings/confluence` | ADR-099 | PARTIAL |
| DELETE | `/guilds/{guild_id}/settings/confluence` | ADR-099 | MISSING |
| POST | `/guilds/{guild_id}/settings/confluence/test` | ADR-099 | MISSING |

### Job Operations
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/jobs` | ADR-013 | PARTIAL |
| GET | `/guilds/{guild_id}/jobs/{job_id}` | ADR-013 | PARTIAL |
| POST | `/guilds/{guild_id}/jobs/{job_id}/cancel` | ADR-013 | MISSING |
| POST | `/guilds/{guild_id}/jobs/{job_id}/pause` | ADR-013 | MISSING |
| POST | `/guilds/{guild_id}/jobs/{job_id}/resume` | ADR-013 | MISSING |
| POST | `/guilds/{guild_id}/jobs/{job_id}/retry` | ADR-013 | MISSING |

### Task Operations
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/summaries/tasks/{task_id}` | - | MISSING |
| POST | `/guilds/{guild_id}/summaries/tasks/{task_id}/cancel` | - | MISSING |

---

## 2. Schedule Management (`schedules.py`) - 9 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/schedules` | ADR-104 | COVERED |
| POST | `/guilds/{guild_id}/schedules` | ADR-104 | COVERED |
| GET | `/guilds/{guild_id}/schedules/{schedule_id}` | ADR-104 | PARTIAL |
| PATCH | `/guilds/{guild_id}/schedules/{schedule_id}` | ADR-104 | COVERED |
| DELETE | `/guilds/{guild_id}/schedules/{schedule_id}` | ADR-104 | COVERED |
| POST | `/guilds/{guild_id}/schedules/{schedule_id}/run` | ADR-104 | PARTIAL |
| GET | `/guilds/{guild_id}/schedules/{schedule_id}/history` | ADR-104 | PARTIAL |
| GET | `/guilds/{guild_id}/schedules/{schedule_id}/rolling-summaries` | ADR-104 | PARTIAL |
| POST | `/guilds/{guild_id}/check-channel-privacy` | ADR-073 | MISSING |

---

## 3. Archive & Retrospective (`archive.py`) - 42 endpoints

### Source Management
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/archive/sources` | - | MISSING |
| DELETE | `/archive/sources/{source_key}` | - | MISSING |
| POST | `/archive/scan` | - | MISSING |

### Job Management
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| POST | `/archive/generate` | - | PARTIAL |
| POST | `/archive/estimate` | - | MISSING |
| GET | `/archive/jobs` | - | PARTIAL |
| GET | `/archive/jobs/{job_id}` | - | PARTIAL |
| POST | `/archive/jobs/{job_id}/cancel` | - | MISSING |
| POST | `/archive/jobs/{job_id}/pause` | - | MISSING |
| POST | `/archive/jobs/{job_id}/resume` | - | MISSING |

### Cost & Reports
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/archive/cost-report` | - | MISSING |
| POST | `/archive/backfill-report` | - | MISSING |

### WhatsApp Import
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| POST | `/archive/import/whatsapp` | ADR-081 | PARTIAL |

### Google Drive Sync (26 endpoints)
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/archive/sync/status` | ADR-091 | MISSING |
| GET | `/archive/sync/servers` | ADR-091 | MISSING |
| POST | `/archive/sync/servers` | ADR-091 | MISSING |
| DELETE | `/archive/sync/servers/{server_id}` | ADR-091 | MISSING |
| POST | `/archive/sync/servers/{server_id}/sync-now` | ADR-091 | MISSING |
| GET | `/archive/oauth/google` | ADR-091 | MISSING |
| GET | `/archive/oauth/google/callback` | ADR-091 | MISSING |
| POST | `/archive/migrate-legacy` | - | MISSING |
| (+ 18 more drive/sync endpoints) | | ADR-091 | MISSING |

---

## 4. Wiki Management (`wiki.py`) - 26 endpoints

### Page Operations
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/wiki/pages` | ADR-056 | COVERED |
| GET | `/guilds/{guild_id}/wiki/pages/{path}` | ADR-056 | PARTIAL |
| POST | `/guilds/{guild_id}/wiki/pages/{path}/synthesize` | ADR-063 | COVERED |
| POST | `/guilds/{guild_id}/wiki/pages/{path}/rate` | ADR-065 | MISSING |

### Navigation & Search
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/wiki/search` | ADR-056 | COVERED |
| GET | `/guilds/{guild_id}/wiki/tree` | ADR-056 | MISSING |
| GET | `/guilds/{guild_id}/wiki/recent` | ADR-056 | MISSING |

### Statistics & Health
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/wiki/stats` | ADR-056 | MISSING |
| GET | `/guilds/{guild_id}/wiki/contradictions` | ADR-064 | MISSING |
| POST | `/guilds/{guild_id}/wiki/contradictions/{id}/resolve` | ADR-064 | MISSING |
| GET | `/guilds/{guild_id}/wiki/orphans` | ADR-056 | MISSING |

### Settings & Jobs
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/wiki/settings` | ADR-076 | MISSING |
| PATCH | `/guilds/{guild_id}/wiki/settings` | ADR-076 | MISSING |
| POST | `/guilds/{guild_id}/wiki/backfill` | ADR-068 | MISSING |
| GET | `/guilds/{guild_id}/wiki/backfill/{job_id}` | ADR-068 | MISSING |
| POST | `/guilds/{guild_id}/wiki/regenerate` | ADR-084 | MISSING |
| POST | `/guilds/{guild_id}/wiki/populate` | ADR-061 | MISSING |
| POST | `/guilds/{guild_id}/wiki/synthesis-job/trigger` | ADR-076 | MISSING |
| POST | `/guilds/{guild_id}/wiki/mark-all-dirty` | - | MISSING |
| GET | `/guilds/{guild_id}/wiki/available-perspectives` | ADR-080 | MISSING |
| DELETE | `/guilds/{guild_id}/wiki/clear` | - | MISSING |

---

## 5. RuVector Knowledge Graph (`ruvector.py`) - 24 endpoints

### Search & Stats
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/ruvector/guilds/{guild_id}/stats` | ADR-057 | MISSING |
| GET | `/ruvector/guilds/{guild_id}/search` | ADR-057 | COVERED |
| GET | `/ruvector/guilds/{guild_id}/units` | ADR-057 | PARTIAL |
| GET | `/ruvector/guilds/{guild_id}/graph` | ADR-057 | COVERED |
| GET | `/ruvector/guilds/{guild_id}/export` | ADR-117 | MISSING |

### Views
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/ruvector/guilds/{guild_id}/units/{unit_id}/related` | ADR-057 | MISSING |
| GET | `/ruvector/guilds/{guild_id}/views/topic/{topic}` | ADR-057 | MISSING |
| GET | `/ruvector/guilds/{guild_id}/views/daily` | ADR-057 | MISSING |
| GET | `/ruvector/guilds/{guild_id}/views/weekly` | ADR-057 | MISSING |

### Learning Signals (ADR-093)
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| POST | `/ruvector/guilds/{guild_id}/learning/click` | ADR-093 | MISSING |
| POST | `/ruvector/guilds/{guild_id}/learning/dwell` | ADR-093 | MISSING |
| POST | `/ruvector/guilds/{guild_id}/learning/feedback` | ADR-093 | MISSING |

### Coherence Validation
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/ruvector/guilds/{guild_id}/coherence/flagged` | ADR-057 | MISSING |
| POST | `/ruvector/guilds/{guild_id}/coherence/flagged/{id}/resolve` | ADR-057 | MISSING |

### Backfill & Processing
| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| POST | `/ruvector/guilds/{guild_id}/backfill` | ADR-057 | MISSING |
| GET | `/ruvector/guilds/{guild_id}/backfill/status` | ADR-057 | MISSING |
| POST | `/ruvector/guilds/{guild_id}/process/{summary_id}` | ADR-057 | MISSING |

---

## 6. Error Management (`errors.py`) - 8 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/errors/health` | - | MISSING |
| GET | `/guilds/{guild_id}/errors` | - | PARTIAL |
| GET | `/guilds/{guild_id}/errors/counts` | - | PARTIAL |
| GET | `/guilds/{guild_id}/errors/{error_id}` | - | PARTIAL |
| POST | `/guilds/{guild_id}/errors/{error_id}/resolve` | - | PARTIAL |
| POST | `/guilds/{guild_id}/errors/{error_id}/retry` | - | MISSING |
| POST | `/guilds/{guild_id}/errors/bulk-resolve` | - | PARTIAL |
| GET | `/guilds/{guild_id}/errors/export` | - | MISSING |

---

## 7. Real-Time Events (`events.py`) - 1 endpoint

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/events` | - | MISSING |

**Note**: Uses in-memory `_event_queues` dict - needs migration to Redis pub/sub.

---

## 8. Feed Management (`feeds.py`) - 9 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/feeds` | - | MISSING |
| POST | `/guilds/{guild_id}/feeds` | - | MISSING |
| GET | `/guilds/{guild_id}/feeds/{feed_id}` | - | MISSING |
| PATCH | `/guilds/{guild_id}/feeds/{feed_id}` | - | MISSING |
| DELETE | `/guilds/{guild_id}/feeds/{feed_id}` | - | MISSING |
| POST | `/guilds/{guild_id}/feeds/{feed_id}/regenerate-token` | - | MISSING |
| GET | `/guilds/{guild_id}/feeds/{feed_id}/preview` | - | MISSING |
| GET | `/feeds/{feed_id}.rss` | - | MISSING |
| GET | `/feeds/{feed_id}.atom` | - | MISSING |

---

## 9. Tenant Management (`tenants.py`) - 21 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/tenants/current` | ADR-079 | MISSING |
| GET | `/tenants/{slug}` | ADR-079 | MISSING |
| PUT | `/tenants/{slug}` | ADR-079 | MISSING |
| GET | `/tenants/{slug}/members` | ADR-079 | MISSING |
| POST | `/tenants/{slug}/members` | ADR-079 | MISSING |
| PUT | `/tenants/{slug}/members/{user_id}` | ADR-079 | MISSING |
| DELETE | `/tenants/{slug}/members/{user_id}` | ADR-079 | MISSING |
| GET | `/tenants/{slug}/admins` | ADR-079 | MISSING |
| POST | `/tenants/{slug}/admins` | ADR-079 | MISSING |
| DELETE | `/tenants/{slug}/admins/{user_id}` | ADR-079 | MISSING |
| GET | `/tenants/{slug}/workspaces` | ADR-079 | MISSING |
| POST | `/tenants/{slug}/workspaces` | ADR-079 | MISSING |
| DELETE | `/tenants/{slug}/workspaces/{workspace_id}` | ADR-079 | MISSING |
| GET | `/tenants/{slug}/branding` | ADR-079 | MISSING |
| PUT | `/tenants/{slug}/branding` | ADR-079 | MISSING |
| GET | `/tenants/{slug}/domain` | ADR-079 | MISSING |
| PUT | `/tenants/{slug}/domain` | ADR-079 | MISSING |
| POST | `/tenants/{slug}/domain/verify` | ADR-079 | MISSING |
| DELETE | `/tenants/{slug}/domain` | ADR-079 | MISSING |
| GET | `/tenants/{slug}/scope` | ADR-079 | MISSING |
| GET | `/tenants/by-domain/{domain}` | ADR-079 | MISSING |

---

## 10. Authentication (`auth.py`) - 6 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/auth/login` | ADR-045 | PARTIAL |
| POST | `/auth/callback` | ADR-045 | PARTIAL |
| POST | `/auth/refresh` | ADR-045 | PARTIAL |
| POST | `/auth/logout` | ADR-045 | PARTIAL |
| GET | `/auth/me` | ADR-045 | PARTIAL |
| POST | `/auth/dev-token` | ADR-045 | MISSING |

---

## 11. Google Auth (`google_auth.py`) - 5 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/google/providers` | ADR-079 | MISSING |
| GET | `/google/login` | ADR-049 | MISSING |
| POST | `/google/callback` | ADR-049 | MISSING |
| GET | `/google/callback` | ADR-049 | MISSING |
| GET | `/google/redirect` | ADR-049 | MISSING |

---

## 12. Guild Configuration (`guilds.py`) - 3 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}` | ADR-073 | MISSING |
| PATCH | `/guilds/{guild_id}/config` | ADR-073 | MISSING |
| POST | `/guilds/{guild_id}/channels/sync` | ADR-073 | MISSING |

---

## 13. Audit Logging (`audit.py`) - 5 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/audit` | ADR-045 | PARTIAL |
| GET | `/guilds/{guild_id}/audit/summary` | ADR-045 | PARTIAL |
| GET | `/guilds/{guild_id}/audit/{entry_id}` | ADR-045 | PARTIAL |
| GET | `/admin/audit` | ADR-045 | MISSING |
| GET | `/admin/audit/summary` | ADR-045 | MISSING |

---

## 14. Slack Integration (`slack.py`) - 13 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| POST | `/slack/install` | ADR-043 | PARTIAL |
| GET | `/slack/oauth/callback` | ADR-043 | MISSING |
| POST | `/slack/events` | ADR-043 | MISSING |
| GET | `/slack/workspaces` | ADR-043 | PARTIAL |
| DELETE | `/slack/workspaces/{workspace_id}` | ADR-043 | MISSING |
| GET | `/slack/workspaces/{workspace_id}/channels` | ADR-043 | PARTIAL |
| POST | `/slack/workspaces/{workspace_id}/sync` | ADR-043 | PARTIAL |
| GET | `/guilds/{guild_id}/slack/links` | ADR-043 | PARTIAL |
| POST | `/guilds/{guild_id}/slack/links` | ADR-043 | MISSING |
| DELETE | `/guilds/{guild_id}/slack/links/{link_id}` | ADR-043 | MISSING |
| GET | `/guilds/{guild_id}/slack/available-workspaces` | ADR-043 | MISSING |
| POST | `/guilds/{guild_id}/slack/test-connection` | ADR-043 | MISSING |
| GET | `/slack/workspaces/{workspace_id}/users` | ADR-043 | MISSING |

---

## 15. WhatsApp Imports (`whatsapp_imports.py`) - 13 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/whatsapp/imports` | ADR-081 | PARTIAL |
| POST | `/guilds/{guild_id}/whatsapp/imports` | ADR-081 | PARTIAL |
| GET | `/guilds/{guild_id}/whatsapp/imports/{import_id}` | ADR-081 | PARTIAL |
| DELETE | `/guilds/{guild_id}/whatsapp/imports/{import_id}` | ADR-081 | MISSING |
| GET | `/guilds/{guild_id}/whatsapp/imports/{import_id}/messages` | ADR-081 | PARTIAL |
| GET | `/guilds/{guild_id}/whatsapp/chats/{chat_id}/participants` | ADR-081 | MISSING |
| PATCH | `/guilds/{guild_id}/whatsapp/participants/{participant_id}` | ADR-081 | MISSING |
| POST | `/guilds/{guild_id}/whatsapp/chats/{chat_id}/participants/merge` | ADR-081 | MISSING |
| POST | `/guilds/{guild_id}/whatsapp/scrub-pii` | ADR-081 | PARTIAL |
| GET | `/guilds/{guild_id}/whatsapp/drive/folders` | ADR-081 | MISSING |
| POST | `/guilds/{guild_id}/whatsapp/drive/import` | ADR-081 | MISSING |
| POST | `/guilds/{guild_id}/whatsapp/migrate-legacy` | ADR-081 | MISSING |
| GET | `/guilds/{guild_id}/whatsapp/coverage` | ADR-112 | MISSING |

---

## 16. Coverage Analysis (`coverage.py`) - 8 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/coverage/summary` | ADR-072 | MISSING |
| POST | `/guilds/{guild_id}/coverage/refresh` | ADR-072 | MISSING |
| GET | `/guilds/{guild_id}/coverage/gaps` | ADR-072 | MISSING |
| POST | `/guilds/{guild_id}/coverage/backfill` | ADR-072 | MISSING |
| GET | `/guilds/{guild_id}/coverage/backfill` | ADR-072 | MISSING |
| POST | `/guilds/{guild_id}/coverage/backfill/pause` | ADR-072 | MISSING |
| POST | `/guilds/{guild_id}/coverage/backfill/resume` | ADR-072 | MISSING |
| DELETE | `/guilds/{guild_id}/coverage/backfill` | ADR-072 | MISSING |

---

## 17. Health Checks (`health.py`) - 3 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/health` | ADR-024 | MISSING |
| GET | `/health/live` | ADR-024 | MISSING |
| GET | `/health/ready` | ADR-024 | MISSING |

---

## 18. Webhooks (`webhooks.py`) - 6 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/webhooks` | - | MISSING |
| POST | `/guilds/{guild_id}/webhooks` | - | MISSING |
| GET | `/guilds/{guild_id}/webhooks/{webhook_id}` | - | MISSING |
| PATCH | `/guilds/{guild_id}/webhooks/{webhook_id}` | - | MISSING |
| DELETE | `/guilds/{guild_id}/webhooks/{webhook_id}` | - | MISSING |
| POST | `/guilds/{guild_id}/webhooks/{webhook_id}/test` | - | MISSING |

---

## 19. Prompt Templates (`prompt_templates.py`) - 7 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/prompt-templates` | ADR-034 | PARTIAL |
| POST | `/guilds/{guild_id}/prompt-templates` | ADR-034 | PARTIAL |
| GET | `/guilds/{guild_id}/prompt-templates/{id}` | ADR-034 | PARTIAL |
| PATCH | `/guilds/{guild_id}/prompt-templates/{id}` | ADR-034 | PARTIAL |
| DELETE | `/guilds/{guild_id}/prompt-templates/{id}` | ADR-034 | PARTIAL |
| GET | `/guilds/{guild_id}/prompt-templates/{id}/usage` | ADR-034 | MISSING |
| POST | `/guilds/{guild_id}/prompt-templates/{id}/duplicate` | ADR-034 | MISSING |

---

## 20. Default Prompts (`prompts.py`) - 2 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/prompts/defaults` | ADR-010 | MISSING |
| GET | `/prompts/defaults/{category}` | ADR-010 | MISSING |

---

## 21. Push Templates (`push_templates.py`) - 4 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/push-templates` | ADR-014 | MISSING |
| POST | `/guilds/{guild_id}/push-templates` | ADR-014 | MISSING |
| POST | `/guilds/{guild_id}/push-templates/preview` | ADR-014 | PARTIAL |
| GET | `/guilds/{guild_id}/push-templates/{id}` | ADR-014 | MISSING |

---

## 22. Issues (`issues.py`) - 5 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/issues/config` | ADR-070 | MISSING |
| POST | `/issues` | ADR-070 | MISSING |
| GET | `/issues` | ADR-070 | MISSING |
| GET | `/issues/github-url` | ADR-070 | MISSING |
| GET | `/issues/my-activity` | ADR-070 | MISSING |

---

## 23. Google Admin Groups (`google_admin_groups.py`) - 3 endpoints

| Method | Endpoint | ADR | Status |
|--------|----------|-----|--------|
| GET | `/guilds/{guild_id}/google-admin-groups` | ADR-050 | MISSING |
| POST | `/guilds/{guild_id}/google-admin-groups` | ADR-050 | MISSING |
| DELETE | `/guilds/{guild_id}/google-admin-groups/{group_email}` | ADR-050 | MISSING |

---

## Summary Statistics

| Route File | Endpoints | Covered | Partial | Missing |
|------------|-----------|---------|---------|---------|
| summaries.py | 37 | 4 | 20 | 13 |
| schedules.py | 9 | 4 | 4 | 1 |
| archive.py | 42 | 0 | 5 | 37 |
| wiki.py | 26 | 3 | 1 | 22 |
| ruvector.py | 24 | 2 | 1 | 21 |
| errors.py | 8 | 0 | 5 | 3 |
| events.py | 1 | 0 | 0 | 1 |
| feeds.py | 9 | 0 | 0 | 9 |
| tenants.py | 21 | 0 | 0 | 21 |
| auth.py | 6 | 0 | 5 | 1 |
| google_auth.py | 5 | 0 | 0 | 5 |
| guilds.py | 3 | 0 | 0 | 3 |
| audit.py | 5 | 0 | 3 | 2 |
| slack.py | 13 | 0 | 5 | 8 |
| whatsapp_imports.py | 13 | 0 | 5 | 8 |
| coverage.py | 8 | 0 | 0 | 8 |
| health.py | 3 | 0 | 0 | 3 |
| webhooks.py | 6 | 0 | 0 | 6 |
| prompt_templates.py | 7 | 0 | 5 | 2 |
| prompts.py | 2 | 0 | 0 | 2 |
| push_templates.py | 4 | 0 | 1 | 3 |
| issues.py | 5 | 0 | 0 | 5 |
| google_admin_groups.py | 3 | 0 | 0 | 3 |
| **TOTAL** | **253** | **9** | **60** | **184** |

---

## ADR Coverage Analysis

| ADR | Title | Endpoints | In Code | In PRD |
|-----|-------|-----------|---------|--------|
| ADR-005 | Summary Delivery | 37 | Yes | Partial |
| ADR-010 | Custom Prompts | 2 | Yes | No |
| ADR-013 | Job Tracking | 6 | Yes | Partial |
| ADR-014 | Push Templates | 4 | Yes | Partial |
| ADR-024 | Health Checks | 3 | Yes | No |
| ADR-030 | Email Delivery | 1 | Yes | Partial |
| ADR-034 | Prompt Templates | 7 | Yes | Partial |
| ADR-043 | Slack Integration | 13 | Yes | Partial |
| ADR-045 | Audit Logging | 11 | Yes | Partial |
| ADR-047 | Discord DM | 1 | Yes | Partial |
| ADR-049 | Google SSO | 5 | Yes | No |
| ADR-050 | Google Admin | 3 | Yes | No |
| ADR-056 | Wiki Core | 26 | Yes | Partial |
| ADR-057 | RuVector | 24 | Yes | Partial |
| ADR-063 | Wiki Synthesis | 1 | Yes | Partial |
| ADR-064 | Wiki Filtering | 2 | Yes | No |
| ADR-065 | Synthesis Rating | 1 | Yes | No |
| ADR-068 | Wiki Backfill | 2 | Yes | No |
| ADR-070 | Issue Tracker | 5 | Yes | No |
| ADR-072 | Coverage | 8 | Yes | No |
| ADR-073 | Channel Privacy | 4 | Yes | No |
| ADR-076 | Auto Synthesis | 3 | Yes | No |
| ADR-079 | Multi-Tenancy | 26 | Yes | No |
| ADR-080 | Perspectives | 1 | Yes | No |
| ADR-081 | WhatsApp Import | 13 | Yes | Partial |
| ADR-084 | Wiki Regen | 2 | Yes | No |
| ADR-091 | Drive Sync | 26 | Yes | No |
| ADR-093 | Learning Signals | 3 | Yes | No |
| ADR-099 | Confluence | 8 | Yes | Partial |
| ADR-104 | Rolling Periods | 9 | Yes | Partial |
| ADR-112 | WhatsApp Coverage | 1 | Yes | No |
| ADR-117 | RVF Export | 1 | Yes | No |

---

*Generated by endpoint audit - 2026-06-02*
