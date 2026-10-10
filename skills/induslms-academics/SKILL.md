---
name: induslms-academics
description: >-
  Indus LMS academics plus school Outlook inbox: announcements,
  assignments (EOL tests + FA/SDL assessments + learning tasks), results
  and feedback, shared teacher resources, messages, notifications,
  attendance, policies and teacher emails; can hand in files, message
  teachers, mark things read and request extensions when the student asks.
  Use for schoolwork, homework, what's due, test scores, notices,
  attendance, or teacher emails. Prefers MCP tools, falls back to repo CLIs.
---

# Indus Academics

Reads freely. **WRITE** tools (send, mark-read, extension requests, hand-ins) change school data: only when the student asks, after showing them exactly what will be sent and getting a yes. Never answer or submit a test for the student. Cite source per item.

## Sources

1. **MCP tools** (`induslms-academics`) — live data, preferred.
2. **CLI fallback** — `lms.py` (LMS), `mailapp.py` (School mail), `outlook.py` (Graph email).

## LMS workflow

1. **Notices**: `list_announcements`, then `list_notifications --unread-only`. `link` routes into LMS (`/assignments/test/.../eol`, `/courses/.../resources/...`).
2. **Assignments**: `assignments_overview [course_id]` merges EOL tests (status/score/`expires_message`), assessments (`due_date`, nested under `assessment`), resources. Report all three. `test-marks/me` PYP-only — DP returns `BAD_REQUEST`, use EOL + assessments. IDs from `list_courses`.
3. **Resources**: `list_resources(course_id)` → usually folders (`is_folder`, `child_count`). Open via `parent_resource_id` (`children <id>`); `?parent=` unfiltered, avoid. `get_resource` → `file_urls[]` (`file_id`, `name`). `download_resource` saves to `~/Downloads/induslms`; read file after when asked about contents. Shapes: `references/endpoints.md`.
4. **Attendance**: `get_attendance` (sessions) + `get_attendance_day` (days + `reason`).
5. **Results & feedback**: `get_eol_result(test_id=row id)` (answers vs correct + AI notes), `get_assessment_submission` / `get_assessment_feedback(assessment.id)`, `get_request_status([ids])` (extension/resubmission limits; `can_request.*` is `{ok, message}`).
6. **Learning tasks**: `list_learning_tasks` + `get_learning_task(id)` (instructions, attachments, submission).
7. **Messages**: `list_message_threads`, `get_conversation(user_id)`, `list_message_contacts`. Sending is a WRITE.
8. **Writes** (on request, confirmed): `send_message`, `mark_notification_read` / `mark_all_notifications_read`, `mark_announcement_read`, `request_extension_or_resubmission` (reason 10–500 chars), `cancel_request`, `submit_assessment_files` / `submit_learning_task` (local files, the student's own work).

## Email workflow

* Prefer Apple Mail.app tools — zero setup: `schoolmail_search [query] [--sender] [--since ISO]`, `schoolmail_read <Mailbox:id>`, `schoolmail_folders`. Account `School`, newest first.
* Graph tools (`outlook_search/read/folders`) = fallback. Need `INDUS_OUTLOOK_CLIENT_ID` + one `outlook.py login`.
* Match teacher emails ↔ `teacher_name/email` from `list_courses`; assignment titles ↔ subjects; inbox notices ↔ announcements.

## Output

Due dates, status, teacher names always. `--json`/raw payloads for agents, summaries for humans. "No token" error → `lms.py login <email>` once; Outlook unconfigured → point at README.
