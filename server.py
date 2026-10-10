#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""IndusLMS MCP server (stdio).

Academic tools (LMS) + school Outlook inbox tools (Graph). Auth comes from
token files created via `lms.py login` / `outlook.py login` (never
committed; see README). The LMS access token is refreshed before it
expires; no tool ever returns a token.

Tools whose description starts with WRITE change school data (messages,
mark-read, extension requests, handing in files). Taking tests (EOL
open/submit, FA question answers) is deliberately not exposed here: a
student answers those themselves in openLMS, the web app or `induslms eol-take`.
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
    token, tenant, _ = lms.session_context()
    return token, tenant


def _ctx_user() -> tuple[str, str, str]:
    token, tenant, user_id = lms.session_context()
    if not user_id:
        raise RuntimeError("Saved token has no user id. Run `induslms login <email>` again.")
    return token, tenant, user_id


MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _local_files(paths: list[str]) -> list[tuple[str, bytes, None]]:
    """Read files to hand in. Refuses hidden paths and the token file, so a
    prompt-injected instruction cannot ship credentials to the LMS."""
    if not paths:
        raise ValueError("Give at least one file path.")
    token_file = os.path.realpath(lms.TOKEN_FILE)
    out = []
    for raw in paths:
        path = os.path.realpath(os.path.expanduser(raw))
        parts = path.split(os.sep)
        if path == token_file or any(p.startswith(".") for p in parts if p):
            raise ValueError(f"Refusing to upload {raw}: hidden files and credentials are never sent.")
        if not os.path.isfile(path):
            raise ValueError(f"No such file: {raw}")
        if os.path.getsize(path) > MAX_UPLOAD_BYTES:
            raise ValueError(f"{raw} is larger than 25 MB.")
        with open(path, "rb") as f:
            out.append((os.path.basename(path), f.read(), None))
    return out


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
def list_eol(limit: int | None = None, offset: int = 0, course_id: str | None = None,
             year: str | None = None) -> dict[str, Any]:
    """Teacher-published end-of-lesson tests with status, score, due messages and attempt flags."""
    token, tid = _ctx()
    return lms.eol_tests(token, tid, limit, offset, course_id=course_id, year=year)


@mcp.tool()
def list_assessments(assessment_type: str | None = None, course_id: str | None = None) -> list[dict[str, Any]]:
    """Every FA/SA assessment (all pages) with due dates, marks and teacher names.
    assessment_type: "FA" or "SA"."""
    token, _ = _ctx()
    return lms.assessments_all(token, assessment_type, course_id)


@mcp.tool()
def get_assessment_submission(assessment_id: str) -> dict[str, Any]:
    """What the student handed in for one FA/SA (files, comment, time). Takes assessment.id."""
    token, _ = _ctx()
    return lms.assessment_submission(token, assessment_id)


@mcp.tool()
def get_assessment_feedback(assessment_id: str) -> dict[str, Any]:
    """Teacher feedback for one FA/SA: total score, comments, rubric scores, annotated files."""
    token, _ = _ctx()
    return lms.assessment_feedback(token, assessment_id)


@mcp.tool()
def get_request_status(assessment_ids: list[str]) -> dict[str, Any]:
    """Extension/resubmission status per assessment (can_request, requests_used/max, latest)."""
    token, _ = _ctx()
    return lms.request_summary(token, assessment_ids)


@mcp.tool()
def get_eol_result(test_id: str) -> dict[str, Any]:
    """A submitted EOL test: score, every answer vs the correct option, AI notes. test_id = row `id` (uuid)."""
    token, tid, uid = _ctx_user()
    return lms.eol_result(token, tid, test_id, uid)


@mcp.tool()
def list_learning_tasks(course_id: str | None = None) -> list[dict[str, Any]]:
    """Learning tasks with instructions, due dates, status, score and attachment links."""
    token, tid = _ctx()
    return lms.learning_tasks(token, tid, course_id)


@mcp.tool()
def get_learning_task(task_id: str) -> dict[str, Any]:
    """One learning task with the student's submission, score and feedback."""
    token, tid = _ctx()
    return lms.learning_task_detail(token, tid, task_id)


@mcp.tool()
def list_announcements_full(academic_year: str | None = None) -> list[dict[str, Any]]:
    """Announcements visible to the student with full HTML bodies, sender and attachment URLs."""
    token, _ = _ctx()
    return lms.announcements_visible(token, academic_year)


@mcp.tool()
def list_message_contacts() -> list[dict[str, Any]]:
    """Teachers and staff the student can message (user_id, name, role, subjects)."""
    token, tid = _ctx()
    return lms.message_contacts(token, tid)


@mcp.tool()
def list_message_threads() -> list[dict[str, Any]]:
    """The student's conversations with their latest message."""
    token, tid = _ctx()
    return lms.message_threads(token, tid)


@mcp.tool()
def get_conversation(user_id: str) -> dict[str, Any]:
    """Messages with one contact, oldest first."""
    token, tid = _ctx()
    return lms.message_conversation(token, tid, user_id)


@mcp.tool()
def list_policies() -> list[dict[str, Any]]:
    """School policy documents (title, version, PDF link)."""
    token, tid = _ctx()
    return lms.policies(token, tid)


@mcp.tool()
def send_message(to_user_id: str, text: str) -> dict[str, Any]:
    """WRITE: send a message to a teacher (user_id from list_message_contacts). Confirm the text with the student first."""
    token, tid = _ctx()
    return lms.send_message(token, tid, to_user_id, text)


@mcp.tool()
def mark_notification_read(notification_id: str) -> dict[str, Any]:
    """WRITE: mark one notification read."""
    token, tid = _ctx()
    return lms.notification_read(token, tid, notification_id)


@mcp.tool()
def mark_all_notifications_read() -> dict[str, Any]:
    """WRITE: mark every notification read."""
    token, tid = _ctx()
    return lms.notifications_read_all(token, tid)


@mcp.tool()
def mark_announcement_read(announcement_id: str) -> dict[str, Any]:
    """WRITE: record that the student has read an announcement."""
    token, _ = _ctx()
    return lms.announcement_read(token, announcement_id)


@mcp.tool()
def request_extension_or_resubmission(assessment_id: str, request_type: str, reason: str,
                                      preferred_due_at: str | None = None) -> dict[str, Any]:
    """WRITE: ask the teacher for an "extension" or "resubmission" on an FA/SA (reason 10-500 chars,
    preferred_due_at ISO 8601). Confirm with the student first."""
    token, _ = _ctx()
    return lms.assessment_request(token, assessment_id, request_type, reason, preferred_due_at)


@mcp.tool()
def cancel_request(request_id: str) -> dict[str, Any]:
    """WRITE: withdraw a pending extension/resubmission request."""
    token, _ = _ctx()
    return lms.request_cancel(token, request_id)


@mcp.tool()
def submit_assessment_files(assessment_id: str, file_paths: list[str], comment: str = "") -> dict[str, Any]:
    """WRITE: hand in an FA/SA as files from this computer (the student's own work). Confirm the
    files with the student first; hidden files and credentials are refused."""
    token, tid = _ctx()
    files = lms.upload_files(token, tid, lms.ASSESSMENT_UPLOAD_MODULE, _local_files(file_paths))
    return lms.assessment_submit_upload(token, assessment_id, [f["file_url"] for f in files], comment)


@mcp.tool()
def submit_learning_task(task_id: str, file_paths: list[str], text: str = "") -> dict[str, Any]:
    """WRITE: hand in a learning task with files from this computer (the student's own work). Confirm
    the files with the student first; hidden files and credentials are refused."""
    token, tid = _ctx()
    files = lms.upload_files(token, tid, lms.TASK_UPLOAD_MODULE, _local_files(file_paths))
    return lms.task_submit(token, tid, task_id, files, text)


@mcp.tool()
def list_notifications(
    limit: int = 20, offset: int = 0, unread_only: bool = False
) -> dict[str, Any]:
    """Notifications with unread_count and deep links (reading never marks them read)."""
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
