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

Tools: `get_profile`, `list_courses`, `list_resources`, `get_resource`, `download_resource`, `assignments_overview`, `list_eol`, `list_assessments`, `list_notifications`, `get_attendance`, `get_attendance_day`, `list_announcements`, `list_calendar`, `schoolmail_search`, `schoolmail_read`, `schoolmail_folders`, `outlook_search`, `outlook_read`, `outlook_folders`.

## School email (Apple Mail.app — no setup)

Mail.app already holds the `School` account, so agents read it via osascript (JXA). No credentials, no app registration:

```bash
python3 mailapp.py folders
python3 mailapp.py search "assignment" --top 5
python3 mailapp.py search --sender teacher@indusschool.com --since 2026-09-01
python3 mailapp.py read Inbox:24203
```

Refs are `Mailbox:id`. Override account/mailbox with `SCHOOL_MAIL_ACCOUNT` / `SCHOOL_MAILBOX`.

### Register in pi

Create `~/.pi/agent/mcp.json` (same shape as `mcp.json` in this repo):

```json
{ "mcpServers": { "induslms-academics": {
  "command": "/path/to/induslms-agent/.venv/bin/python",
  "args": ["/path/to/induslms-agent/server.py"],
  "cwd": "/path/to/induslms-agent"
} } }
```

Use the venv python — system python lacks `mcp`/`msal`. Restart pi afterwards.

### Register in opencode

In `~/.config/opencode/opencode.jsonc` under `mcp`:

```json
"induslms-academics": {
  "type": "local",
  "command": ["/path/to/induslms-agent/.venv/bin/python", "/path/to/induslms-agent/server.py"],
  "cwd": "/path/to/induslms-agent",
  "enabled": true,
  "timeout": 15000
}
```

Restart opencode afterwards. Verify with a prompt like
"list my courses using induslms-academics".

## Skill (workflow guidance)

`skills/induslms-academics/SKILL.md` teaches the workflow:
announcements → assignments → resources/download → attendance,
plus School inbox. Install (copies to pi `~/.pi/agent/skills/`
and opencode `~/.config/opencode/skills/`):

```bash
bash scripts/install-skill.sh
```

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

## Outlook (school inbox via Microsoft Graph)

Read-only (`Mail.Read` delegated, device-code flow). Token cache at
`~/.indus_outlook_token.json` — never in repo.

```bash
# 1. Entra ID -> App registrations -> New: allow public client flows,
#    add delegated Mail.Read. Multitenant OK.
export INDUS_OUTLOOK_CLIENT_ID=<app/client id>
python3 outlook.py login        # approve code in browser
python3 outlook.py search "assignment" --top 5
python3 outlook.py search --sender teacher@indusschool.com --since 2026-09-01
python3 outlook.py read <message_id>
```

MCP tools: `outlook_search`, `outlook_read`, `outlook_folders`
(same coverage; unconfigured → clear error, not crash).
School tenant blocks user consent → IT admin must grant admin consent first.
