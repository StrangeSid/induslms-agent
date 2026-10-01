---
name: induslms-academics
description: >-
  Read-only access to Indus LMS academics: announcements, assignments
  (EOL tests + FA/SDL assessments), shared teacher resources (list, open
  folders, download files), notifications, and attendance. Use whenever the
  user asks about schoolwork, homework, what teachers shared, what's due,
  test scores, notices, or attendance. Prefers MCP tools when available,
  falls back to the induslms CLI.
---

# Indus LMS Academics

Give the student their academic context from Indus LMS. Read-only — never attempt to submit, mark-read, or mutate anything.

## Data sources (priority order)

1. **MCP tools** (`induslms-academics` server) — live data, preferred.
2. **CLI fallback** — `python3 /path/to/induslms-agent/lms.py ...` (same functions).

## Workflow

### 1. Announcements first
* `list_announcements` (or `lms.py announcements`). School-wide notices.
* Then `list_notifications --unread-only` for personal items (EOL published, resources shared). Notification `link` fields route into the LMS (`/assignments/test/.../eol`, `/courses/.../resources/...`).

### 2. Assignments (what's due / scores)
* `assignments_overview [course_id]` merges three sources — always report all three:
  * **EOL tests**: teacher-published, have `status` (assigned/submitted/graded), `score/total_marks`, `expires_message` (due).
  * **Assessments**: FA/SDL tasks, `due_date`, `teacher_name`, nested under `assessment`.
  * **Shared resources**: teacher materials for the course.
* `test-marks/me` is PYP-only — on DP accounts it returns `BAD_REQUEST`. Say so and use EOL + assessments instead.
* Course IDs come from `list_courses` (DP 2026-27; e.g. CS01 `bdbc1c79-...`, teacher names included).

### 3. Shared resources (files from teachers)
* `list_resources(course_id)` → top level is usually **folders** (`is_folder`, `child_count`).
* Open folders with `parent_resource_id` (`list_resources` / `children <folder_id>`). Do NOT use `?parent=` — it returns unfiltered results.
* `get_resource(id)` shows `file_urls[]` with `file_id` + `name`.
* `download_resource(resource_id, file_id)` saves to `~/Downloads/induslms` and returns the path. Read the file after downloading when the user asks about its contents.
* See `references/endpoints.md` for exact URL shapes.

### 4. Attendance cross-check
* `get_attendance` = session summary (present/total, percentage). `get_attendance_day` = day breakdown with `reason` (e.g. ISL Camp). Report both when asked about attendance.

## Output rules
* Cite source per item (EOL / assessment / resource / announcement / notification).
* Include due dates, status, and teacher names where available.
* `--json` (CLI) / raw tool payloads when another agent consumes the output; human summaries otherwise.
* If the MCP server reports "No LMS token", tell the user to run `python3 lms.py login <email>` once.
