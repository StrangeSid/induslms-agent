#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
"""IndusLMS MCP server (stdio, read-only).

Academic tools (LMS) + school Outlook inbox tools (Graph). No login,
no mark-read, no send, no submissions — auth comes from token files created
via `lms.py login` / `outlook.py login` (never committed; see README).
"""

from __future__ import annotations

import os
from typing import Any

try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv()
except Exception:
    pass

from mcp.server.fastmcp import FastMCP

import lms
import mailapp

mcp = FastMCP("induslms-academics")


def _ctx() -> tuple[str, str]:
    token_data = lms.load_token()
    if not token_data or not token_data.get("access"):
        raise RuntimeError("No LMS token. Run `python lms.py login <email>` first.")
    token = token_data["access"]
    roles = (token_data.get("user") or {}).get("roles") or []
    tenant = roles[0].get("tenant_id") if roles else None
    tenant = tenant or os.environ.get("INDUSLMS_TENANT")
    if not tenant:
        raise RuntimeError("No tenant ID. Set INDUSLMS_TENANT or re-login.")
    return token, tenant


@mcp.tool()
def get_profile() -> dict[str, Any]:
    """Current student profile (email, full name, id)."""
    token, _ = _ctx()
    return lms.me(token)


@mcp.tool()
def list_courses(year: str | None = None) -> dict[str, Any]:
    """Student courses with teachers and class IDs (DP program)."""
    token, tenant = _ctx()
    return lms.my_courses(token, tenant, year)


@mcp.tool()
def list_resources(
    course_id: str | None = None,
    parent_resource_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Shared teacher resources (folders + files). Use parent_resource_id to open a folder."""
    token, tid = _ctx()
    return lms.list_resources(token, tid, course_id, parent_resource_id, page, page_size)


@mcp.tool()
def get_resource(resource_id: str) -> dict[str, Any]:
    """One resource's metadata: folder flag, child_count, file_urls with file_ids."""
    token, tid = _ctx()
    return lms.get_resource(token, tid, resource_id)


@mcp.tool()
def download_resource(resource_id: str, file_id: str) -> dict[str, Any]:
    """Download a shared file to ~/Downloads/induslms. Returns path, size, content-type."""
    token, tid = _ctx()
    return lms.download_resource_file(token, tid, resource_id, file_id)


@mcp.tool()
def assignments_overview(course_id: str | None = None) -> dict[str, Any]:
    """Unified assignments: EOL tests + assessments + shared resources (raw payloads)."""
    token, tid = _ctx()
    return lms.assignments_overview(token, tid, course_id)


@mcp.tool()
def list_eol(limit: int | None = None, offset: int = 0) -> dict[str, Any]:
    """Teacher-published end-of-lesson tests with status, score, due messages."""
    token, tid = _ctx()
    return lms.eol_tests(token, tid, limit, offset)


@mcp.tool()
def list_assessments() -> dict[str, Any]:
    """FA/SDL assessments with due dates and teacher names."""
    token, _ = _ctx()
    return lms.assessments(token)


@mcp.tool()
def list_notifications(
    limit: int = 20, offset: int = 0, unread_only: bool = False
) -> dict[str, Any]:
    """Notifications with unread_count and deep links (read-only; no mark-read)."""
    token, tid = _ctx()
    return lms.notifications(token, tid, limit, offset, unread_only)


@mcp.tool()
def get_attendance() -> dict[str, Any]:
    """Attendance summary + session records (percentage, present/absent)."""
    token, _ = _ctx()
    return lms.attendance(token)


@mcp.tool()
def get_attendance_day() -> dict[str, Any]:
    """Day-wise attendance breakdown (working days, per-date status/reason)."""
    token, tid = _ctx()
    return lms.attendance_day(token, tid)


@mcp.tool()
def list_announcements(tenant: str | None = None, academic_year: str | None = None) -> dict[str, Any]:
    """School announcements, optionally filtered by tenant/year."""
    token, _ = _ctx()
    return lms.announcements(token, tenant, academic_year)


@mcp.tool()
def list_calendar() -> dict[str, Any]:
    """School calendar events."""
    token, _ = _ctx()
    return lms.calendar_events(token)


def _outlook():
    import outlook  # deferred: msal only needed for email tools

    if not os.environ.get(outlook.CLIENT_ID_ENV):
        raise RuntimeError(
            f"Outlook not configured. Set {outlook.CLIENT_ID_ENV}, "
            "then run `python3 outlook.py login`. See README."
        )
    return outlook


@mcp.tool()
def outlook_search(
    query: str | None = None,
    sender: str | None = None,
    since: str | None = None,
    top: int = 10,
) -> dict[str, Any]:
    """Search school Outlook inbox (teacher emails, assignment notices). since = ISO date."""
    return _outlook().search_inbox(query, sender, since, top)


@mcp.tool()
def outlook_read(message_id: str, max_body: int = 4000) -> dict[str, Any]:
    """Read one Outlook message (subject, from, date, truncated body)."""
    return _outlook().read_message(message_id, min(max_body, 8000))


@mcp.tool()
def outlook_folders() -> dict[str, Any]:
    """Outlook mail folders with unread/total counts."""
    return _outlook().list_folders()


@mcp.tool()
def schoolmail_search(
    query: str | None = None,
    sender: str | None = None,
    since: str | None = None,
    top: int = 10,
    mailbox: str = "Inbox",
) -> dict[str, Any]:
    """Search School inbox in Apple Mail.app (no setup; newest first). since = ISO date."""
    return mailapp.search_inbox(query, sender, since, top, mailbox)


@mcp.tool()
def schoolmail_read(ref: str, max_body: int = 4000) -> dict[str, Any]:
    """Read one School email by ref 'Mailbox:id' (subject, from, date, body)."""
    return mailapp.read_message(ref, min(max_body, 8000))


@mcp.tool()
def schoolmail_folders() -> dict[str, Any]:
    """School account mailboxes with message counts."""
    return mailapp.list_folders()


def _sharepoint():
    import sharepoint  # deferred: msal only needed for file tools

    try:
        import msal  # noqa: F401
    except Exception as e:
        raise RuntimeError(f"msal not installed: {e}")
    return sharepoint


@mcp.tool()
def od_resolve_link(link: str) -> dict[str, Any]:
    """Resolve a OneDrive/SharePoint sharing link (from mail) to file metadata + folder children."""
    return _sharepoint().resolve_link(link)


@mcp.tool()
def od_browse(path: str = "/", site_id: str | None = None) -> dict[str, Any]:
    """List a OneDrive folder by path (or a SharePoint default-drive folder with site_id)."""
    return _sharepoint().browse(path, site_id)


@mcp.tool()
def od_download(target: str) -> dict[str, Any]:
    """Download a OneDrive/SharePoint file by item id or sharing link to ~/Downloads/induslms."""
    return _sharepoint().download(target)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
