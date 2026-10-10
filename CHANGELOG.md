# Changelog

All notable changes, newest first. Versioning is manual (`pyproject.toml` + git tag).

## 0.4.0 — unreleased

- **Writes** (read-only rule lifted): `eol_open` / `eol_submit` / `eol_proctor_event` / `eol_explain`, `assessment_submit_questions` / `assessment_submit_upload` / `assessment_resubmit`, `assessment_request` / `request_cancel`, `upload_file(s)` (S3 presigned PUT; modules `assignment_submission` and the LMS's own `assesement` spelling), `task_submit`, `send_message`, `notification_read` / `notifications_read_all`, `announcement_read`. All go through `api()`, raise `LMSError(status, code, message)` and never retry.
- **More reads**: `assessments_all` (all pages), `assessment_submission` / `assessment_feedback` (by `assessment.id`), `request_summary` (50 ids per call), `eol_result`, `eol_feedback`, `learning_tasks`, `learning_task_detail`, `announcements_visible` (full HTML + `file_urls`), `message_contacts` / `message_threads` / `message_conversation` (oldest first), `program_years`, `policies` (all programme years, deduped), `help_articles`; `eol_tests(course_id=, year=)`.
- **Speed**: one pooled keep-alive `requests.Session` (`lms.HTTP`) for every call. A fresh TLS handshake per request cost ~1 s from India vs ~0.28 s on a reused connection (measured Oct 2026).
- **Tokens**: `ensure_fresh_token()` refreshes before expiry and saves the rotated pair (0600); used by the CLI, `doctor` and the MCP server. `save_token(quiet=True)` keeps MCP stdout clean.
- **CLI**: detail commands (`fa-submission`, `fa-feedback`, `fa-requests`, `eol-result`, `eol-feedback`, `tasks`, `task`, `announcements-visible`, `contacts`, `threads`, `conversation`, `years`, `policies`, `help-articles`) and confirmed writes (`eol-take`, `fa-submit`, `fa-request`, `request-cancel`, `task-submit`, `send`, `notification-read`, `notifications-read-all`, `announcement-read`; `--yes` skips the prompt).
- **MCP**: 41 tools (+11 reads, +8 `WRITE:` tools). Test-taking is deliberately not exposed. Upload tools refuse hidden paths and the token file.
- Tests: `tests/test_writes.py` (paths, payloads, error mapping, token refresh, upload safety; offline).

## 0.3.1 — 2026-10-05

- License is now GPL-3.0-or-later only (`COPYING`); README rehaul, `CONTRIBUTING.md`, `CHANGELOG.md`

## 0.3.0 — 2026-10-05

- OneDrive / SharePoint via Microsoft Graph (`sharepoint.py`, `od_resolve_link`, `od_browse`, `od_download`)
- No-registration auth: `INDUS_USE_BUILTIN_CLIENT=1` uses the pre-consented Microsoft Office client
- MCP schemas slimmed: tenant resolved server-side, `max_body` clamped
- General-purpose `examples/update-resources.prompt.md`

## 0.2.0 — 2026-10-04

- One-command `./install.sh`, `lms.py doctor`, `.env` autoload, `INDUSLMS_TOKEN_FILE` support
- Multi-host configs (pi, opencode, Claude Code/Desktop, OpenAI) + `examples/`
- PyPI trusted-publisher workflow

## 0.1.0 — 2026-10-01

- Read-only LMS CLI + MCP server + skill (announcements, assignments, resources, attendance)
- School inbox via Apple Mail (osascript) and Outlook Graph; sanitized for public release
