#!/usr/bin/env python3
"""IndusLMS MCP server (stdio, read-only).

Exposes agent-safe tools for announcements, assignments, shared resources,
notifications, and attendance. No login, no mark-read, no submissions —
authentication comes from the existing token file created via `lms.py login`
(never committed; see README).
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

import lms

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


def _tid(explicit: str | None) -> tuple[str, str]:
    token, default_tenant = _ctx()
    return token, explicit or default_tenant


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
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Shared teacher resources (folders + files). Use parent_resource_id to open a folder."""
    token, tid = _tid(tenant_id)
    return lms.list_resources(token, tid, course_id, parent_resource_id, page, page_size)


@mcp.tool()
def get_resource(resource_id: str, tenant_id: str | None = None) -> dict[str, Any]:
    """One resource's metadata: folder flag, child_count, file_urls with file_ids."""
    token, tid = _tid(tenant_id)
    return lms.get_resource(token, tid, resource_id)


@mcp.tool()
def download_resource(
    resource_id: str, file_id: str, tenant_id: str | None = None
) -> dict[str, Any]:
    """Download a shared file to ~/Downloads/induslms. Returns path, size, content-type."""
    token, tid = _tid(tenant_id)
    return lms.download_resource_file(token, tid, resource_id, file_id)


@mcp.tool()
def assignments_overview(
    course_id: str | None = None, tenant_id: str | None = None
) -> dict[str, Any]:
    """Unified assignments: EOL tests + assessments + shared resources (raw payloads)."""
    token, tid = _tid(tenant_id)
    return lms.assignments_overview(token, tid, course_id)


@mcp.tool()
def list_eol(limit: int | None = None, offset: int = 0, tenant_id: str | None = None) -> dict[str, Any]:
    """Teacher-published end-of-lesson tests with status, score, due messages."""
    token, tid = _tid(tenant_id)
    return lms.eol_tests(token, tid, limit, offset)


@mcp.tool()
def list_assessments() -> dict[str, Any]:
    """FA/SDL assessments with due dates and teacher names."""
    token, _ = _ctx()
    return lms.assessments(token)


@mcp.tool()
def list_notifications(
    limit: int = 20, offset: int = 0, unread_only: bool = False, tenant_id: str | None = None
) -> dict[str, Any]:
    """Notifications with unread_count and deep links (read-only; no mark-read)."""
    token, tid = _tid(tenant_id)
    return lms.notifications(token, tid, limit, offset, unread_only)


@mcp.tool()
def get_attendance() -> dict[str, Any]:
    """Attendance summary + session records (percentage, present/absent)."""
    token, _ = _ctx()
    return lms.attendance(token)


@mcp.tool()
def get_attendance_day(tenant_id: str | None = None) -> dict[str, Any]:
    """Day-wise attendance breakdown (working days, per-date status/reason)."""
    token, tid = _tid(tenant_id)
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
