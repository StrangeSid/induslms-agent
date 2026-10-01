# Indus LMS endpoint reference (verified live, Oct 2026)

Base: `https://api.induslms.com`, header `Authorization: Bearer <access>`,
`Origin: https://induslms.com`. Token from `POST /api/v1/auth/login/`
`{email, password}` → `{access, refresh, user}`.

## Academics

| Purpose | Method + path |
|---|---|
| Profile | `GET /api/v1/auth/me/` |
| Courses | `GET /api/v1/tenants/{tid}/me/student/courses?include_classes=true&include_teachers=true` |
| Resources top-level | `GET /api/v1/tenants/{tid}/resources/?course_id={cid}&page=&page_size=` |
| Resource children | `GET /api/v1/tenants/{tid}/resources/?parent_resource_id={rid}` (NOT `?parent=`) |
| Resource detail | `GET /api/v1/tenants/{tid}/resources/{rid}/` |
| File content | `GET /api/v1/tenants/{tid}/resources/{rid}/files/{fid}/content/?disposition=attachment\|inline` (binary) |
| EOL tests | `GET /api/v1/tenants/{tid}/eol-tests/my/` |
| Assessments | `GET /api/v1/student/assessments/` |
| Test marks (PYP only) | `GET /api/v1/tenants/{tid}/pyp/courses/{cid}/test-marks/me/` — DP → `BAD_REQUEST` |
| DP projects | `GET /api/v1/tenants/{tid}/dp-projects/` (empty `[]` for this student) |
| DP section | `GET /api/v1/tenants/{tid}/dp-projects/student/{pid}/{ee\|tok\|cas\|exhibition\|...}/` |
| Notifications | `GET /api/v1/tenants/{tid}/notifications/?limit=&offset=` + client-side `is_read` filter |
| Attendance summary | `GET /api/v1/students/me/attendance/` |
| Attendance days | `GET /api/v1/tenants/{tid}/students/me/attendance/day/` |
| Announcements | `GET /api/announcements/` (`?tenant=&academic_year=`) |
| Calendar | `GET /api/v1/school-calendar/events/` |
| Reports | `GET /api/v2/report-engine/student-pdfs/` |

## Shapes worth knowing

* Resource: `{id, title, is_folder, child_count, teacher_name, course_id, file_urls: [{file_id, name, download_url}]}`. Folders have empty `file_urls`; files have `child_count: 0`.
* EOL item: `{title, subject, topic, status, score, total_marks, expires_message, available_until}`.
* Assessment wrapper: `{status, submitted_at, assessment: {title, subject, due_date, teacher_name, instructions}}`.
* Notification: `{type (eol|fa|resource), title, message, link, course_id, is_read}`.
* Frontend route `/assignments?courseId=&classId=` maps to EOL + resources (no single backend endpoint — hence the aggregator).
