# IndusLMS Agent

Read-only agent access to Indus LMS academics: **announcements, assignments, shared resources, notifications, attendance**. For `pi` + `opencode` harnesses via **MCP + Skill + CLI** (Outlook deferred to a later phase).

## Quickstart

```bash
cd /path/to/induslms-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Authenticate once (token saved OUTSIDE the repo)
python3 lms.py login you@indusschool.com
# or: INDUSLMS_EMAIL=... INDUSLMS_PASS=... python3 lms.py login

# CLI
python3 lms.py courses
python3 lms.py assignments --course <course_id>
python3 lms.py resources --course <course_id>
python3 lms.py children <folder_id>
python3 lms.py download <resource_id> <file_id> --out /tmp/induslms-test
python3 lms.py notifications --unread-only --limit 5
python3 lms.py attendance && python3 lms.py attendance-day
```

Tokens live at `~/.induslms_token.json` (override with `INDUSLMS_TOKEN_FILE` in a future release; currently `lms.TOKEN_FILE`). Never committed — see `.gitignore`.

## MCP server (recommended for agents)

Stdio, read-only tools only (no login, no mark-read, no submissions):

```bash
python3 server.py
```

Tools: `get_profile`, `list_courses`, `list_resources`, `get_resource`, `download_resource`, `assignments_overview`, `list_eol`, `list_assessments`, `list_notifications`, `get_attendance`, `get_attendance_day`, `list_announcements`, `list_calendar`.

### Register in pi

Add to your pi MCP config (`~/.pi/` agent config or project `mcp.json` — see `mcp.json` in this repo for the exact block):

```json
{ "mcpServers": { "induslms-academics": {
  "command": "python",
  "args": ["/path/to/induslms-agent/server.py"]
} } }
```

### Register in opencode

Add to `~/.config/opencode/opencode.jsonc` under `mcp`:

```json
"induslms-academics": {
  "type": "local",
  "command": ["python", "/path/to/induslms-agent/server.py"],
  "enabled": true
}
```

(Adjust to your opencode version's local-stdio syntax; `mcp.json` here is the canonical reference.)

## Skill (workflow guidance)

`skills/induslms/SKILL.md` teaches agents the academic workflow: announcements → assignments → resources/download → attendance cross-check. Install:

```bash
bash scripts/install-skill.sh
```

This copies the skill into the pi and opencode skill dirs. See the SKILL.md for details.

## Key API notes (reverse-engineered, verified live)

* Base `https://api.induslms.com`, `Authorization: Bearer <access>` from `POST /api/v1/auth/login/`.
* Resources: `GET /api/v1/tenants/{tid}/resources/?course_id=` for top level; children via `?parent_resource_id={rid}` (NOT `?parent=`, which returns unfiltered results). Files: `.../resources/{rid}/files/{fid}/content/?disposition=attachment|inline` (binary, streamed).
* Assignments = EOL tests (`/eol-tests/my/`, 23 items) + student assessments (`/student/assessments/`, 6 items) + resources. `test-marks/me` is PYP-only (DP gets `BAD_REQUEST`) — handled gracefully.
* DP projects endpoint returns `[]` for this student; section fetcher ready for when IDs exist.
* Notifications support `?limit=&offset=`; unread filter is client-side (`is_read`) so `--limit 5 --unread-only` may return fewer rows — use a larger limit.
* Attendance has two shapes: session summary (`/students/me/attendance/`) and day breakdown (`/tenants/{tid}/students/me/attendance/day/`).

## Security

* Read-only by design. The only POSTs in the codebase are `login` and the (CLI-unused) token-refresh helper — the MCP server exposes neither.
* Credentials via env/prompt only; tokens outside the repo; `.gitignore` blocks `*token*.json`, `.env`, downloads.

## Outlook (deferred)

School Outlook inbox via Microsoft Graph (device-code, `Mail.Read`) is planned as Phase D. Not in v0.1.0.
