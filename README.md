# IndusLMS Agent

Read-only agent access to Indus LMS academics: **announcements, assignments, shared resources, notifications, attendance**. For `pi` + `opencode` harnesses via **MCP + Skill + CLI**.

## Quickstart (one command)

```bash
git clone https://github.com/StrangeSid/induslms-agent.git
cd induslms-agent
./install.sh
```

This creates `.venv`, installs the package, runs `lms.py login`,
merges MCP configs for pi + opencode, installs the skill, and runs
`lms.py doctor`. Restart your agent host afterwards.

Manual setup (if you prefer):

> Replace `/path/to/induslms-agent` with your checkout path and
> `you@indusschool.com` with your school email.

```bash
cd /path/to/induslms-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e .  # or: pip install -r requirements.txt

cp .env.example .env  # then fill INDUSLMS_EMAIL/PASS/TENANT (.env auto-loaded)
# Authenticate once (token saved OUTSIDE the repo)
python3 lms.py login you@indusschool.com
# or: INDUSLMS_EMAIL=... INDUSLMS_PASS=... python3 lms.py login

# Health check
python3 lms.py doctor
# CLI
python3 lms.py courses
python3 lms.py assignments --course <course_id>
python3 lms.py resources --course <course_id>
python3 lms.py children <folder_id>
python3 lms.py download <resource_id> <file_id> --out /tmp/induslms-test
python3 lms.py notifications --unread-only --limit 5
python3 lms.py attendance && python3 lms.py attendance-day
```

Tokens live at `~/.induslms_token.json` (override with `INDUSLMS_TOKEN_FILE`). Never committed — see `.gitignore`.

## Credentials (`.env`) — used by programs, never sent to the LLM

```bash
cp .env.example .env   # then fill in your own values
```

| Variable | Used by | Never leaves your machine |
|---|---|---|
| `INDUSLMS_EMAIL` / `INDUSLMS_PASS` | `lms.py login` only (one POST, then discarded) | ✅ |
| `INDUSLMS_TENANT` | Tenant fallback when the token has no roles | ✅ |
| `INDUSLMS_TOKEN_FILE` | Where the JWT is cached (`~/.induslms_token.json`) | ✅ |
| `INDUS_OUTLOOK_CLIENT_ID` | Graph device-code login (`outlook.py login`) | ✅ |

How it stays private:

* `lms.py`, `outlook.py`, `server.py` load `.env` via `python-dotenv` at startup — values live only in the local process environment.
* The MCP server exposes **no** login/token tools, and no tool ever returns passwords, tokens, or client IDs — tools return school data (assignments, mail, attendance) only.
* `.gitignore` blocks `.env`, `*token*.json`, and downloads, so credentials can't be committed by accident. Share only `.env.example` (empty values).

PyPI (after release): `pipx install induslms-agent` or `uvx induslms-agent doctor`,
then `induslms login you@indusschool.com` + `induslms-server` as your MCP command.

## MCP server (recommended for agents)

Stdio, read-only tools only (no login, no mark-read, no submissions):

```bash
python3 server.py
```

Tools: `get_profile`, `list_courses`, `list_resources`, `get_resource`, `download_resource`, `assignments_overview`, `list_eol`, `list_assessments`, `list_notifications`, `get_attendance`, `get_attendance_day`, `list_announcements`, `list_calendar`, `schoolmail_search`, `schoolmail_read`, `schoolmail_folders`, `outlook_search`, `outlook_read`, `outlook_folders`, `od_resolve_link`, `od_browse`, `od_download`.

Run with `python3 server.py` (or `induslms-server` after `pip install`). Copy-paste
configs live in `examples/`: `.mcp.json` (Claude Code project scope),
`claude_desktop_config.json.example`, `opencode.jsonc.example`,
`mcp-uvx.json.example` (PyPI/uvx form).

## School email (Apple Mail.app — macOS only)

Mail.app already holds the `School` account, so agents read it via osascript (JXA). No credentials, no app registration. On Linux/Windows `schoolmail_*` reports unavailable — use `outlook_*` instead:

```bash
python3 mailapp.py folders
python3 mailapp.py search "assignment" --top 5
python3 mailapp.py search --sender teacher@indusschool.com --since 2026-09-01
python3 mailapp.py read Inbox:24203
```

Refs are `Mailbox:id`. Override account/mailbox with `SCHOOL_MAIL_ACCOUNT` / `SCHOOL_MAILBOX`.

### Register in pi

Create `~/.pi/agent/mcp.json` (same shape as `mcp.json` in this repo,
with `/path/to/induslms-agent` replaced by your checkout path):

```json
{ "mcpServers": { "induslms-academics": {
  "command": "/path/to/induslms-agent/.venv/bin/python",
  "args": ["/path/to/induslms-agent/server.py"],
  "cwd": "/path/to/induslms-agent"
} } }
```

Use the venv python — system python lacks `mcp`/`msal`. Restart pi afterwards.

### Register in opencode

In `~/.config/opencode/opencode.jsonc` under `mcp` (replace
`/path/to/induslms-agent` with your checkout path):

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

### Claude Code

```bash
claude mcp add induslms-academics -- /path/to/induslms-agent/.venv/bin/python /path/to/induslms-agent/server.py
# or project scope: copy .mcp.json (replace paths), then: claude mcp list
```

Skill: `bash scripts/install-skill.sh` also copies to `~/.claude/skills/`
(`INSTALL_PROJECT_SKILL=1` for `.claude/skills/`).

### Claude Desktop

Copy `examples/claude_desktop_config.json.example` into
`~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS; see file for Win/Linux paths), replace paths, relaunch.

### OpenAI-compatible agents (code, no config file)

```python
from agents.mcp import MCPServerStdio
async with MCPServerStdio(
    params={"command": "/path/to/induslms-agent/.venv/bin/python",
            "args": ["/path/to/induslms-agent/server.py"]},
    cache_tools_list=True,
) as server:
    ...
```

Hosted MCP / GPT Actions need a public HTTPS endpoint (not provided;
stdio-only by design).

## Skill (workflow guidance)

`skills/induslms-academics/SKILL.md` teaches the workflow:
announcements → assignments → resources/download → attendance,
plus School inbox. Install (copies to pi, opencode, and Claude skills):

```bash
bash scripts/install-skill.sh
```

### End-user prompt: refresh local school materials

`examples/update-resources.prompt.md` is a copy-paste template that
checks LMS + the School mailbox for new teacher materials, downloads
only what's missing into a `School/` folder, and parses everything to
text. Fill in your subjects/teachers, paste it into a fresh agent
session.

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
# ..or skip registration: export INDUS_USE_BUILTIN_CLIENT=1 (sign in as yourself)
python3 outlook.py login        # approve code in browser
python3 outlook.py search "assignment" --top 5
python3 outlook.py search --sender teacher@indusschool.com --since 2026-09-01
python3 outlook.py read <message_id>
```

MCP tools: `outlook_search`, `outlook_read`, `outlook_folders`
(same coverage; unconfigured → clear error, not crash).
School tenant blocks user consent → IT admin must grant admin consent first
(not needed with `INDUS_USE_BUILTIN_CLIENT=1`).

## OneDrive / SharePoint (school files via Microsoft Graph)

Read-only (`Files.Read` + `Sites.Read.All`, same device-code flow and token
cache as Outlook — re-run login once to consent to the new scopes):

```bash
python3 sharepoint.py login
python3 sharepoint.py resolve <sharing-link-from-mail>  # shared file/folder metadata
python3 sharepoint.py browse /                          # your OneDrive root
python3 sharepoint.py download <item-id-or-link> --out /tmp/school
```

MCP tools: `od_resolve_link`, `od_browse`, `od_download`. No local OneDrive
sync client needed — pure HTTPS, works on any OS.
