# IndusLMS Agent

[![PyPI](https://img.shields.io/pypi/v/induslms-agent)](https://pypi.org/project/induslms-agent/)
[![Python](https://img.shields.io/pypi/pyversions/induslms-agent)](https://pypi.org/project/induslms-agent/)
[![License](https://img.shields.io/badge/license-MIT%20OR%20GPL--3.0-blue)](LICENSE-MIT)

Read-only agent access to Indus LMS academics — announcements, assignments, shared resources, notifications, attendance — plus school email and OneDrive files. For `pi`, `opencode`, Claude Code/Desktop, and OpenAI-compatible agents via **MCP + Skill + CLI**.

> [!NOTE]
> This project is read-only by design. Nothing here can submit work, mark notifications read, send mail, or mutate school data.

## Quickstart

```bash
git clone https://github.com/StrangeSid/induslms-agent.git
cd induslms-agent
./install.sh
```

`install.sh` creates `.venv`, installs the package, logs you in, wires up MCP configs for pi + opencode, installs the skill, and runs a health check. Then restart your agent host and ask: *"list my courses using induslms-academics"*.

<details>
<summary>Manual setup (if you prefer)</summary>

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .  # or: pip install -r requirements.txt
cp .env.example .env  # fill in your values (auto-loaded, never committed)
python3 lms.py login you@school.example
python3 lms.py doctor  # health check
```

Or from PyPI: `pipx install induslms-agent` (or `uvx induslms-agent doctor`), then `induslms login you@school.example` and use `induslms-server` as your MCP command.

</details>

## Configuration

| Variable | Purpose |
|---|---|
| `INDUSLMS_EMAIL` / `INDUSLMS_PASS` | Used once by `lms.py login`, then discarded |
| `INDUSLMS_TENANT` | Tenant fallback when the token has no roles |
| `INDUSLMS_TOKEN_FILE` | Token cache path (default `~/.induslms_token.json`) |
| `INDUS_OUTLOOK_CLIENT_ID` | Your Entra app id for Graph login |
| `INDUS_USE_BUILTIN_CLIENT=1` | Alternative: no registration — sign in as yourself via the pre-consented Microsoft Office client |

Credentials live only in your local process environment. The MCP server exposes no login/token tools, no tool ever returns secrets, and `.gitignore` blocks `.env`, `*token*.json`, and downloads.

## MCP server

Stdio, 22 tools. Run with `python3 server.py` (or `induslms-server` after install).

| Group | Tools |
|---|---|
| LMS academics | `get_profile`, `list_courses`, `list_resources`, `get_resource`, `download_resource`, `assignments_overview`, `list_eol`, `list_assessments`, `list_notifications`, `get_attendance`, `get_attendance_day`, `list_announcements`, `list_calendar` |
| Mail (macOS, no setup) | `schoolmail_search`, `schoolmail_read`, `schoolmail_folders` |
| Mail (Graph, any OS) | `outlook_search`, `outlook_read`, `outlook_folders` |
| Files (Graph, any OS) | `od_resolve_link`, `od_browse`, `od_download` |

Connect your host (replace `/path/to` with your checkout; ready-made files in `examples/`):

| Host | Config |
|---|---|
| pi | `~/.pi/agent/mcp.json` (or run `./install.sh`, which merges it) |
| opencode | `~/.config/opencode/opencode.jsonc` under `mcp` (v1) or `mcp.servers` (v2) |
| Claude Code | `claude mcp add induslms-academics -- <venv-python> <checkout>/server.py`, or copy `.mcp.json` |
| Claude Desktop | paste `examples/claude_desktop_config.json.example` into `claude_desktop_config.json`, relaunch |
| OpenAI SDK | `MCPServerStdio` with `{command: <venv-python>, args: [server.py]}`; hosted MCP/GPT Actions need public HTTPS (not provided, stdio-only by design) |

## School email

- **Apple Mail.app (macOS, zero setup):** `python3 mailapp.py search "assignment" --top 5` — reads the existing `School` account via osascript. On other platforms these tools report unavailable; use Outlook instead.
- **Outlook/Graph (any OS):** `python3 outlook.py login` (approve the code in your browser), then `search` / `read` / `folders`. Needs `Mail.Read`: your own app id + one admin consent, or `INDUS_USE_BUILTIN_CLIENT=1` for no-registration sign-in.

## OneDrive / SharePoint files (any OS)

Same device-code flow and token cache as Outlook, plus `Files.Read` + `Sites.Read.All` (re-run login once to consent):

```bash
python3 sharepoint.py login
python3 sharepoint.py resolve <sharing-link-from-mail>
python3 sharepoint.py browse /
python3 sharepoint.py download <item-id-or-link> --out /tmp/school
```

No sync client needed — pure HTTPS. Teacher sharing links pasted from mail resolve directly.

## Skill + prompt template

- **Skill** (`skills/induslms-academics/`): workflow guidance for agents (notices → assignments → resources → attendance + inbox). Install: `bash scripts/install-skill.sh` (pi, opencode, Claude).
- **Prompt** (`examples/update-resources.prompt.md`): copy-paste template that refreshes a local `School/` folder from LMS + mailbox. Fill in your subjects/teachers, paste into a fresh agent session.
- **API reference**: `skills/induslms-academics/references/endpoints.md` (reverse-engineered endpoints, verified live).

## Contributing, changelog, license

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md). Dual-licensed **MIT or GPL-3.0-or-later** — see [LICENSE-MIT](LICENSE-MIT) and [COPYING](COPYING).
