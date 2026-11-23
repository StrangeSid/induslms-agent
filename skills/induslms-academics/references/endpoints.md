# Indus LMS endpoint reference (verified live, Oct 2026)

Base: `https://api.induslms.com`, header `Authorization: Bearer <access>`,
`Origin: https://induslms.com`. Token from `POST /api/v1/auth/login/`
`{email, password}` → `{access, refresh, user}`.

## Academics

| Purpose | Method + path |
|---|---|
| Profile | `GET /api/v1/auth/me/` |
| Courses | `GET /api/v1/tenants/{tid}/me/student/courses?include_classes=true&include_teachers=true` |
| Resources top-level | `GET /api/v1/tenants/{tid}/resources/?course_id={cid}&page=&page_size=` (scope by enrolled course_id to avoid 403) |
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
* Resource permission & scoping: Unfiltered queries (`/resources/` without `course_id`) return school-wide resources across all grades; crawling or accessing resources outside the student's enrolled grade/class returns HTTP 403 (`"Not allowed for your grade"`). Always scope top-level listings with `course_id` obtained from `list_courses`. If a resource yields 403, handle gracefully as grade-restricted.
* EOL item: `{title, subject, topic, status, score, total_marks, expires_message, available_until}`.
* Assessment wrapper: `{status, submitted_at, assessment: {title, subject, due_date, teacher_name, instructions}}`.
* Notification: `{type (eol|fa|resource), title, message, link, course_id, is_read}`.
* Frontend route `/assignments?courseId=&classId=` maps to EOL + resources (no single backend endpoint — hence the aggregator).

## Details (verified live, Oct 9 2026)

| Purpose | Method + path |
|---|---|
| EOL list, filtered | `GET /api/v1/tenants/{tid}/eol-tests/my/?year=2026-27` or `?course_id={cid}` (per-course lists can miss tests from courses outside the student's list; the global list is the superset) |
| EOL result | `GET /api/v1/tenants/{tid}/eol-tests/{test_uuid}/students/{user_id}/` → `{submission_id, score{score,total_marks,percentage,submitted_at}, responses[{question_id,question_text,selected_option,correct_option,is_correct,marks_awarded,ai_explanation,options{a..d{text,image}}}]}` |
| EOL teacher feedback | `GET /api/v1/tenants/{tid}/eol-tests/{test_uuid}/feedback/` → `{feedbacks: []}` |
| FA/SA list, all pages | `GET /api/v1/student/assessments/?assessment_type=FA&page=&page_size=100` |
| FA/SA submission / feedback | `GET /api/v1/student/assessments/{assessment.id}/submission/` and `/feedback/` (the **assessment** id; the wrapper `assignment_id` 404s) |
| Extension/resubmission status | `GET /api/v1/student/requests/summary/?assessment_ids={csv}` → `{enabled, requests_max, reason_min_length, reason_max_length, items{aid: {can_request{extension,resubmission: {ok, code, message}}, latest{extension, resubmission}, requests_used, past_due, effective_due_date, resubmission_window_open}}}` |
| Learning tasks | `GET /api/v1/tenants/{tid}/assignments/student/list/[?course_id=]` → `[{id,title,instructions,due_date,status,score,grade,feedback_text,attachments[{name,file_url}]}]`; detail `.../assignments/student/{id}/detail/` |
| Announcements (full) | `GET /api/announcements/visible/?academic_year=2026-27` → list with HTML `message`, `creator`, `file_urls[{url,type}]`, `target_type` |
| Messaging | `GET /api/v1/tenants/{tid}/messages/contacts/`, `.../messages/threads/`, `.../messages/conversation/{user_id}/` (newest first; `{id,from_user_id,to_user_id,text,sent_at,read_at,status}`) |
| Programme years | `GET /api/v1/programs/year-list/?tenant_id={tid}&is_active=true` → `[{program_year_id, program_type, academic_year}]` |
| Policies | `GET /api/v1/tenants/{tid}/academic-years/{program_year_id}/policies/` (the web app reads every year and dedupes by title) |
| Help | `GET /api/v1/tenants/{tid}/help/?audience=student` |

## Parents (verified live, Nov 23 2026)

A parent token reads a child through the parent routes and the student routes
with `?student_id={student_profile_id}`. `student_profile_id` is the
`parents/me/children` id; report-engine `student-pdfs` is the exception and
takes the child's `user_id`.

| Purpose | Method + path |
|---|---|
| Children | `GET /api/v1/parents/me/children` → `{count, results: [{student_profile_id, user_id, full_name, email, status, current_program_year_id, program_name, program_code, program_type, academic_year, current_class_grade, current_class_section, current_class_label}]}` |
| Child courses | `GET /api/v1/tenants/{tid}/parents/me/children/{spid}/courses/?year=&include_teachers=true&include_classes=true` |
| Child calendar | `GET /api/v1/tenants/{tid}/parents/me/children/{spid}/calendar/?from=&to=` (`from`/`to`; `count` + `events[{kind, title, subject, at, course_id, source_id, meta}]`) |
| Attendance summary (all children) | `GET /api/v1/parents/me/attendance/?from_date=&to_date=` → `[{student_id (profile), student_name, attendance_start_date, totals..., percentage, attendance[...]}]` |
| Child learner profile | `GET /api/v1/parents/children/{spid}/learner-profile?year=` |
| Help | `GET /api/v1/tenants/{tid}/help/?audience=parent` |
| Festival banners | `GET /api/v1/festival-banners/active/?role=parent[&grade=][&program_year_id=]` |

Child-scoped reads (each accepts `student_id={spid}`): assessments
(`/api/v1/student/assessments/`), assessment submission/feedback
(`/api/v1/student/assessments/{aid}/submission|feedback/`), EOL list
(`/eol-tests/my/`), learning tasks list/detail, resources list/detail,
notifications, announcements visible, message contacts, attendance day
(`/students/me/attendance/day/?from_date=&to_date=&student_id=`).

Parent denials (do not retry with impersonation):
`GET .../eol-tests/{test_id}/students/{user_id}/` → 403 (no answer review);
`GET /api/v1/assessments/context/` → 403;
`GET /api/v1/tenants/{tid}/policies/` and `.../students/me/attendance/` → 404;
`.../me/student/courses?student_id=` → 404 (use the parent child-courses route).
Parents can mark notifications/announcements read and send messages
(`POST .../messages/ {to_user_id, text}`), but cannot submit work.

## Writes (bundle + live traces; `lms.py` functions in brackets)

| Action | Call |
|---|---|
| Open EOL [`eol_open`] | `POST /api/v1/tenants/{tid}/eol-tests/open/ {test_id: SHORT_ID, passcode}` → `{id: uuid, questions[...], already_submitted}` |
| Submit EOL [`eol_submit`] | `POST .../eol-tests/{uuid}/submit/ {test_id: uuid, passcode, answers[{question_id, selected_option}]}` → `201 {score, total_marks, percent, submitted_at}` |
| Proctoring [`eol_proctor_event`] | `POST .../eol-tests/{uuid}/proctoring/ {event_type: "document_visibility_hidden"}` → `{proctor_violation_count, suspend_threshold, proctor_suspended}`. The web app sends one each time the tab is hidden mid-test and counts mid-test exits locally (max 3). |
| AI note [`eol_explain`] | `POST .../eol-tests/{test_id}/students/{user_id}/question-explanations/ {submission_id, question_id, question_text, options{a..d: text}, selected_option, correct_option, is_correct}` |
| Upload [`upload_file`] | `POST /api/v1/s3uploads/get-upload-url/ {tenant_id, module, entity_id, filename, content_type}` → `{upload_url, file_url, method}`, then `PUT upload_url` (no auth header). Modules: `assignment_submission` (tasks), `assesement` (FA/SA, sic). |
| Task hand-in [`task_submit`] | `POST .../assignments/student/{id}/submit/ {submission_text, submission_files[{file_url, name, content_type, size_bytes}]}` |
| FA/SA hand-in | `POST /api/v1/student/assessments/{aid}/submit-questions/ {responses[{question_id, selected_option|answer_text}], submission_urls, comment}` or `.../submit-upload/ {submission_urls[file_url], comment, assessment_id}`; `.../resubmit/ {keep_indexes, new_files, base_submitted_at?, comment?}` |
| Requests | `POST /api/v1/student/assessments/{aid}/requests/ {request_type: extension|resubmission, reason, preferred_due_at?}`; `POST /api/v1/student/requests/{id}/cancel/` |
| Messages | `POST /api/v1/tenants/{tid}/messages/ {to_user_id, text}` → stored message |
| Mark read | `POST /api/v1/tenants/{tid}/notifications/{id}/read/`, `.../notifications/read-all/`, `POST /api/announcements/{id}/read/` |

Errors come back as `{code, message, status, request_id}` (Indus) or DRF `{detail}`; `lms.LMSError` carries `status`, `code` and the message.
