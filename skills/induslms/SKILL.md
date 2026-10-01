---
name: induslms-academics
description: >-
  Read-only Indus LMS academics plus school Outlook inbox: announcements,
  assignments (EOL tests + FA/SDL assessments), shared teacher resources
  (list, open folders, download files), notifications, attendance, and
  teacher emails. Use for schoolwork, homework, what's due, test scores,
  notices, attendance, or teacher emails. Prefers MCP tools, falls back
  to repo CLIs.
---

# Indus Academics

Read-only — never submit, mark-read, send, or mutate. Cite source per item.

## Sources

1. **MCP tools** (`induslms-academics`) — live data, preferred.
2. **CLI fallback** — `lms.py` (LMS), `outlook.py` (email) in repo root.

## LMS workflow

1. **Notices**: `list_announcements`, then `list_notifications --unread-only`. `link` routes into LMS (`/assignments/test/.../eol`, `/courses/.../resources/...`).
2. **Assignments**: `assignments_overview [course_id]` merges EOL tests (status/score/`expires_message`), assessments (`due_date`, nested under `assessment`), resources. Report all three. `test-marks/me` PYP-only — DP returns `BAD_REQUEST`, use EOL + assessments. IDs from `list_courses`.
3. **Resources**: `list_resources(course_id)` → usually folders (`is_folder`, `child_count`). Open via `parent_resource_id` (`children <id>`); `?parent=` unfiltered, avoid. `get_resource` → `file_urls[]` (`file_id`, `name`). `download_resource` saves to `~/Downloads/induslms`; read file after when asked about contents. Shapes: `references/endpoints.md`.
4. **Attendance**: `get_attendance` (sessions) + `get_attendance_day` (days + `reason`).

## Email workflow

* `outlook_search [query] [--sender] [--since ISO]`, `outlook_read <id>`, `outlook_folders`. Needs `INDUS_OUTLOOK_CLIENT_ID` + one `outlook.py login`.
* Match teacher emails ↔ `teacher_name/email` from `list_courses`; assignment titles ↔ subjects; inbox notices ↔ announcements.

## Output

Due dates, status, teacher names always. `--json`/raw payloads for agents, summaries for humans. "No token" error → `lms.py login <email>` once; Outlook unconfigured → point at README.
