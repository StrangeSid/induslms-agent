# Changelog

All notable changes, newest first. Versioning is manual (`pyproject.toml` + git tag).

## 0.3.1 — 2026-10-05

- License is now GPL-3.0-or-later only (`COPYING`); README rehaul, `CONTRIBUTING.md`, `CHANGELOG.md`

## 0.3.0 — 2026-10-05

- OneDrive / SharePoint via Microsoft Graph (`sharepoint.py`, `od_resolve_link`, `od_browse`, `od_download`)
- No-registration auth: `INDUS_USE_BUILTIN_CLIENT=1` uses the pre-consented Microsoft Office client
- MCP schemas slimmed: tenant resolved server-side, `max_body` clamped
- General-purpose `examples/update-resources.prompt.md`

## 0.2.0 — 2026-10-04

- One-command `./install.sh`, `lms.py doctor`, `.env` autoload, `INDUSLMS_TOKEN_FILE` support
- Multi-host configs (pi, opencode, Claude Code/Desktop, OpenAI) + `examples/`
- PyPI trusted-publisher workflow

## 0.1.0 — 2026-10-01

- Read-only LMS CLI + MCP server + skill (announcements, assignments, resources, attendance)
- School inbox via Apple Mail (osascript) and Outlook Graph; sanitized for public release
