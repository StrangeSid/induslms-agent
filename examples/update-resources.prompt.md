# Prompt: Update school resources from LMS + teacher email

Use this prompt to refresh a local `School/` folder with newly shared
teacher materials. Paste it into a fresh agent session after filling in
the placeholders in `<>`.

---

GOAL
----
Check Indus LMS and the School mailbox for any NEW materials shared by
my teachers since the last update. Download only what is missing,
organise it into `School/`, and parse every new file into plain text
under `Processed_Text (LLM Use)/`. Read-only everywhere:
never submit, mark-read, send, or delete anything.

MY SUBJECTS & TEACHERS
----------------------
Fill in your own subjects and teachers (example rows below):

- Math HL      -> Teacher Name <teacher1@school.example>
- English SL   -> Teacher Name <teacher2@school.example>

Note: LMS course enrolment may name different staff for shared
resources than the class teacher. Trust the teacher list above
for email; accept any teacher's LMS resources for the matching subject.

DIRECTORY CONVENTIONS (follow exactly)
--------------------------------------
- Root: `School/` (e.g. `~/Downloads/School/`)
- One folder per subject, exact names matching your subjects
  (e.g. `Math HL`, `English SL`), plus `Exam Syllabus` for general
  exam material.
- Mirror teacher LMS folder names as subfolders (e.g. a topic or unit
  name shared by the teacher).
- Parsed-text mirror: `Processed_Text (LLM Use)/<same subject>/<same
  subfolder>/<basename>.txt` (single .txt extension).
- Link-only shares (no file): append the URL to the subject's
  `WebResources.txt`, never create empty .txt files for them.
- Images/photos: OCR with tesseract. If OCR yields nothing (e.g. art
  photos), write one line:
  `Visual material: <description> (<basename>). No machine-readable
  text — analyse the image file directly.`
- Skip mailbox signature images (image.png, Outlook-*.png), quiz-reminder
  mails with no attachments, and extracurricular brochures unless they
  are study material.

WORKFLOW
--------
1. AUTH
   - Load the LMS token file (default `~/.induslms_token.json`,
     override with `INDUSLMS_TOKEN_FILE`). If the access token is
     expired, refresh it ONCE via `POST <api-base>/api/token/refresh/`
     and SAVE the new access+refresh pair immediately (rotation
     invalidates the old refresh token after a single use).
   - If refresh fails, STOP and ask the user to run:
     `python3 lms.py login <you@school.example>`
     Do not proceed to LMS steps without valid auth. Email steps can
     still run (Mail.app needs no token).

2. LMS SWEEP (per subject)
   - GET courses (re-fetch the tenant ID via `courses`; do not
     hard-code course or tenant IDs across school years).
   - List top-level resources per course_id (page_size 50), then children
     of each folder via `?parent_resource_id=` (NOT `?parent=`), recursing
     one more level for nested folders.
   - Deduplicate: the same origin_resource_id often appears as received
     copies in other teachers' classes — keep one copy, prefer the
     student's own class.
   - Record: unread notifications, new EOL tests / FA-SDL assessments with
     due dates, scores, and expiry (informational; nothing to download).

3. EMAIL SWEEP (per teacher, School inbox via Mail.app, read-only)
   - Search `--sender <teacher email> --since <last-update date>`, top 30.
     Always sender-filtered: unfiltered or broad-subject scans hang
     Mail.app's scripting bridge on large inboxes.
   - Run searches SEQUENTIALLY (parallel osascript calls wedge Mail.app;
     kill strays with `pkill -f osascript` if a call hangs past 120 s).
   - For each candidate mail, read it and list attachments. New
     file attachments -> download; links/questions -> WebResources.txt or
     a small task .txt (see conventions).

4. DIFF & DOWNLOAD
   - Compare every LMS file and mail attachment against local files by
     name AND content (sizes/hashes — same names with different hashes
     are different versions; keep both).
   - Download missing files straight into their final subject folders
     (LMS: `download_resource_file`, attachment disposition; mail:
     save attachment after confirming the download succeeded).
   - If an LMS file returns 403 on both attachment and inline
     dispositions, skip it and report it as a sharing-permission issue
     for the teacher to fix.

5. PARSE TO TEXT (every new file, no exceptions)
   - `.pdf`  -> `pdftotext -layout`
   - `.docx` -> `python-docx` (paragraphs + tables)
   - `.pptx` -> unzip slide XML, extract `<a:t>` nodes (textutil returns
     empty on these files)
   - images (jpg/png/webp/avif) -> PIL normalise + `tesseract -l eng`
     (`fra` for French text images)
   - Verify: zero-byte .txt outputs get the visual-material placeholder
     line; spot-check one .txt per subject for real content.

6. REPORT
   - Per subject: teacher, what was new (count + destination folders),
     what was already local, links recorded.
   - Flag: pending EOL/FA-SDL tests with expiry dates, 403-blocked
     files, enrolment vs teacher mismatches, mails from unknown teachers.

SUBAGENTS (harness with Task/worker support)
--------------------------------------------
Parallelise per subject. Spawn one worker per subject, each owning
steps 2-5 for ONLY its subject; the coordinator does step 1 (auth),
step 6 (report), and owns shared writes (WebResources.txt edits must
be sequential to avoid clobbering — workers return links, the
coordinator appends them).
- Worker brief must include: subject, teacher name+email, course_id,
  own class_id, subject folder paths, last-update date, and the parse
  commands for its file types. Workers return: files added (src->dest),
  .txt outputs, links found, blocked items, pending tests.
- If the harness has no subagent support, run the subjects sequentially
  in a fixed order (keeps Mail.app calls spaced).

TOOL REFERENCES
---------------
- LMS CLI: `lms.py`
  (`courses | resources --course CID | children TID RID |
   download TID RID FID --out DIR | notifications --unread-only`)
- Mail CLI: `mailapp.py`
  (`search --sender E --since DATE --top 30 [--json] | read Mailbox:id`)
- Skill: `induslms-academics` (workflow + API endpoint reference)
- Token: LMS token file (never commit, never print; see `.env.example`)
