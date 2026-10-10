#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
IndusLMS Agent Tool
API Base: https://api.induslms.com
Auth: JWT Bearer tokens from /api/v1/auth/login/

Reads and writes. Functions that change school data (submitting work,
opening/submitting tests, messaging, marking things read, extension
requests) are grouped under "Writes" below and never retry on their own.
"""

import base64
import json
import mimetypes
import os
import sys
import time
import uuid
from typing import Optional, Dict, Any

import requests
from requests.adapters import HTTPAdapter

try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv()
except Exception:
    pass

API_BASE = "https://api.induslms.com"
TOKEN_FILE = os.path.expanduser(os.environ.get("INDUSLMS_TOKEN_FILE", "~/.induslms_token.json"))

HEADERS_BASE = {
    "Content-Type": "application/json",
    "Origin": "https://induslms.com",
    "Referer": "https://induslms.com/",
}

# One keep-alive session for every call. A fresh TLS connection to
# api.induslms.com costs ~3 round trips (~1 s per request from India,
# measured Oct 2026) versus ~280 ms on a reused connection. Thread-safe
# for concurrent requests; no default auth headers, so presigned S3
# uploads can share it.
HTTP = requests.Session()
HTTP.mount("https://", HTTPAdapter(pool_connections=8, pool_maxsize=32))

# S3 upload modules, spelled exactly as the LMS expects (sic).
TASK_UPLOAD_MODULE = "assignment_submission"
ASSESSMENT_UPLOAD_MODULE = "assesement"


def save_token(data: dict, quiet: bool = False):
    """Save token data to file (0600). `quiet` keeps stdout clean for the MCP server."""
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    if not quiet:
        print(f"[+] Token saved to {TOKEN_FILE}")


def load_token() -> Optional[dict]:
    """Load token data from file."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            return json.load(f)
    return None


def get_auth_headers(token: str) -> dict:
    """Get headers with Bearer token."""
    return {**HEADERS_BASE, "Authorization": f"Bearer {token}"}


def login(email: str, password: str) -> dict:
    """Login to IndusLMS and save tokens."""
    url = f"{API_BASE}/api/v1/auth/login/"
    payload = {"email": email, "password": password}
    headers = {**HEADERS_BASE}

    print(f"[*] Logging in to {url}")
    r = HTTP.post(url, json=payload, headers=headers, timeout=15)
    print(f"[*] Status: {r.status_code}")

    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    if r.ok:
        save_token(data)
        print(f"[+] Login successful for {data.get('user', {}).get('email', 'unknown')}")
        roles = data.get('user', {}).get('roles', [])
        for role in roles:
            print(f"    Role: {role.get('key')} in tenant {role.get('tenant_id')}")
    return data


def refresh_token(refresh: str) -> dict:
    """Refresh access token using refresh token."""
    url = f"{API_BASE}/api/token/refresh/"
    payload = {"refresh": refresh}
    headers = {**HEADERS_BASE}
    r = HTTP.post(url, json=payload, headers=headers, timeout=15)
    return r.json()


def me(token: str) -> dict:
    """Get current user profile."""
    url = f"{API_BASE}/api/v1/auth/me/"
    return HTTP.get(url, headers=get_auth_headers(token), timeout=15).json()


def profile(token: str) -> dict:
    """Get detailed profile."""
    url = f"{API_BASE}/api/v1/profile/me/"
    return HTTP.get(url, headers=get_auth_headers(token), timeout=15).json()


def my_courses(token: str, tenant_id: str, year: str = None, include_classes=True) -> dict:
    """Get student courses for a tenant."""
    params = []
    if year:
        params.append(f"year={year}")
    params.append(f"include_classes={str(include_classes).lower()}")
    params.append("include_teachers=true")
    param_str = "&".join(params)
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/me/student/courses?{param_str}"
    return HTTP.get(url, headers=get_auth_headers(token), timeout=15).json()


def api_get_json(token: str, path: str, params: dict = None, timeout: int = 15):
    """GET helper that returns parsed JSON (dict or list) or an error dict."""
    url = f"{API_BASE}{path}" if path.startswith("/") else path
    r = HTTP.get(url, headers=get_auth_headers(token), params=params, timeout=timeout)
    try:
        return r.json()
    except Exception:
        return {"status": r.status_code, "text": r.text[:2000]}


def attendance(token: str) -> dict:
    """Get student attendance summary + session records (read-only)."""
    url = f"{API_BASE}/api/v1/students/me/attendance/"
    return HTTP.get(url, headers=get_auth_headers(token), timeout=15).json()


def attendance_day(token: str, tenant_id: str) -> dict:
    """Get day-wise attendance breakdown for the tenant (read-only).

    Returns {total_working_days, present_days, absent_days, ...,
             attendance_percentage, records: [{date, status, reason, class}]}.
    """
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/students/me/attendance/day/"
    return HTTP.get(url, headers=get_auth_headers(token), timeout=15).json()


def summarize_attendance(summary: dict, day: dict = None) -> str:
    """Human-readable attendance summary."""
    lines = []
    lines.append(
        f"Sessions: {summary.get('present', '?')}/{summary.get('total_sessions', '?')} present "
        f"({summary.get('percentage', '?')}%), absent={summary.get('absent', '?')}, "
        f"late={summary.get('late', '?')}, excused={summary.get('excused', '?')}"
    )
    if day and isinstance(day, dict):
        lines.append(
            f"Days: {day.get('present_days', '?')}/{day.get('total_working_days', '?')} present "
            f"({day.get('attendance_percentage', '?')}%), absent_days={day.get('absent_days', '?')}"
        )
    for rec in (summary.get("records") or [])[:10]:
        lines.append(
            f"  {rec.get('date')} {rec.get('course_name') or rec.get('subject')} "
            f"[{rec.get('status') if 'status' in rec else 'session'}]"
        )
    if day and isinstance(day, dict):
        for rec in (day.get("records") or [])[:15]:
            lines.append(f"  {rec.get('date')} day={rec.get('status')} {rec.get('reason') or ''}".rstrip())
    return "\n".join(lines)


def notifications(token: str, tenant_id: str, limit=20, offset=0, unread_only=False) -> dict:
    """Get notifications. Reading never marks anything read; use
    notification_read() / notifications_read_all() for that.

    Server supports ?limit=&offset=. unread_only is applied client-side
    via is_read.
    """
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/notifications/?limit={limit}&offset={offset}"
    data = HTTP.get(url, headers=get_auth_headers(token), timeout=15).json()
    if unread_only and isinstance(data, dict) and isinstance(data.get("results"), list):
        data = {**data, "results": [r for r in data["results"] if not r.get("is_read")]}
    return data


def summarize_notifications(data: dict, limit_rows: int = 20) -> str:
    """Human-readable notification list."""
    if not isinstance(data, dict):
        return str(data)[:1000]
    lines = [f"unread={data.get('unread_count', '?')} (showing {min(len(data.get('results', [])), limit_rows)})"]
    for r in (data.get("results") or [])[:limit_rows]:
        state = "UNREAD" if not r.get("is_read") else "read"
        lines.append(
            f"  [{state}] [{r.get('type')}] {r.get('title')} — {(r.get('message') or '')[:100]}"
        )
        if r.get("link"):
            lines.append(f"           link={r.get('link')} course={r.get('course_id')}")
    return "\n".join(lines)


def announcements(token: str, tenant: str = None, year: str = None) -> dict:
    """Get school announcements."""
    url = f"{API_BASE}/api/announcements/"
    params = {}
    if tenant:
        params["tenant"] = tenant
    if year:
        params["academic_year"] = year
    return HTTP.get(url, headers=get_auth_headers(token), params=params, timeout=15).json()


def calendar_events(token: str) -> dict:
    """Get school calendar events."""
    url = f"{API_BASE}/api/v1/school-calendar/events/"
    return HTTP.get(url, headers=get_auth_headers(token), timeout=15).json()


def assessments(token: str, params: dict = None) -> dict:
    """Get student assessments."""
    url = f"{API_BASE}/api/v1/student/assessments/"
    return HTTP.get(url, headers=get_auth_headers(token), params=params, timeout=15).json()


def eol_tests(token: str, tenant_id: str, limit: int = None, offset: int = 0,
              course_id: str = None, year: str = None) -> dict:
    """Get EOL (end-of-lesson) tests — these are teacher-published assignments.

    Server returns the full list (count ~23); limit/offset are applied
    client-side so output stays stable even if the API ignores the params.
    `course_id` narrows to one subject (it can drop tests from courses
    outside the student's course list, so prefer the global list);
    `year` is the academic year, e.g. "2026-27". Rows carry `id` (uuid),
    `short_id` (what the open call takes) and the attempt flags
    (`can_attempt`, `is_expired`, `attempts_blocked`, `proctor_suspended`, ...).
    """
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/eol-tests/my/"
    params = {k: v for k, v in (("course_id", course_id), ("year", year)) if v}
    data = HTTP.get(url, headers=get_auth_headers(token), params=params or None, timeout=15).json()
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        results = data["results"]
        if offset:
            results = results[offset:]
        if limit is not None:
            results = results[:limit]
        data = {**data, "results": results, "limit": limit, "offset": offset}
    return data


def test_marks_me(token: str, tenant_id: str, course_id: str) -> dict:
    """Get PYP test-marks for one course. DP courses return BAD_REQUEST
    ('Course must belong to a PYP programme.') — callers must handle that."""
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/pyp/courses/{course_id}/test-marks/me/"
    return HTTP.get(url, headers=get_auth_headers(token), timeout=15).json()


def dp_projects(token: str, tenant_id: str):
    """List DP project containers for the tenant (returns [] when none).

    Returns a list (not a dict) — keep as-is so callers can len() it.
    """
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/dp-projects/"
    r = HTTP.get(url, headers=get_auth_headers(token), timeout=15)
    try:
        return r.json()
    except Exception:
        return {"status": r.status_code, "text": r.text[:2000]}


def dp_student_section(token: str, tenant_id: str, project_id: str, section: str) -> dict:
    """Fetch one DP student-project section (read-only).

    section like: ee, ee/essay, ee/plan, ee/proposal, ee/rpf, ee/rrs,
    tok, tok/essay, cas, exhibition, reflective-project/assessment, etc.
    e.g. dp_student_section(tok, tid, pid, "ee/essay").
    """
    section = section.strip("/")
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/dp-projects/student/{project_id}/{section}/"
    return HTTP.get(url, headers=get_auth_headers(token), timeout=15).json()


def list_resources(
    token: str,
    tenant_id: str,
    course_id: str = None,
    parent_resource_id: str = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List shared teacher resources (folders + files), read-only.

    - Top-level per course: ?course_id={cid}
    - Children of a folder: ?parent_resource_id={rid} (verified working;
      ?parent= also works but returns unfiltered results — avoid it).
    - All resources: omit course_id (paginated, count ~87).
    """
    params = {"page": page, "page_size": page_size}
    if course_id:
        params["course_id"] = course_id
    if parent_resource_id:
        params["parent_resource_id"] = parent_resource_id
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/resources/"
    return HTTP.get(url, headers=get_auth_headers(token), params=params, timeout=15).json()


def get_resource(token: str, tenant_id: str, resource_id: str) -> dict:
    """Get one resource's metadata (folder flag, child_count, file_urls)."""
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/resources/{resource_id}/"
    return HTTP.get(url, headers=get_auth_headers(token), timeout=15).json()


def summarize_resources(data: dict, limit_rows: int = 30) -> str:
    """Human-readable resource list: folders vs files, teacher, counts."""
    if not isinstance(data, dict):
        return str(data)[:1000]
    lines = [f"count={data.get('count', '?')} (showing up to {limit_rows})"]
    for r in (data.get("results") or [])[:limit_rows]:
        kind = "FOLDER" if r.get("is_folder") else "FILE"
        files = r.get("file_urls") or []
        extra = ""
        if not r.get("is_folder") and files:
            names = ", ".join(f.get("name", "?") for f in files[:3])
            extra = f" files=[{names}]"
        elif r.get("is_folder"):
            extra = f" children={r.get('child_count', '?')}"
        lines.append(
            f"  [{kind}] {r.get('title')} (id={r.get('id')})"
            f" teacher={r.get('teacher_name')}{extra}"
        )
    if data.get("next"):
        lines.append("  ... more pages available (use --page 2)")
    return "\n".join(lines)


def download_resource_file(
    token: str,
    tenant_id: str,
    resource_id: str,
    file_id: str,
    out_dir: str = None,
    disposition: str = "attachment",
    timeout: int = 60,
) -> dict:
    """Download one shared file to disk (read-only GET, streaming).

    Endpoint: GET .../resources/{rid}/files/{fid}/content/?disposition=...
    Returns {path, size_bytes, content_type, filename}. Never parses as JSON.
    """
    import re

    if out_dir is None:
        out_dir = os.path.expanduser("~/Downloads/induslms")
    os.makedirs(out_dir, exist_ok=True)
    url = (
        f"{API_BASE}/api/v1/tenants/{tenant_id}/resources/{resource_id}/"
        f"files/{file_id}/content/?disposition={disposition}"
    )
    r = HTTP.get(url, headers=get_auth_headers(token), timeout=timeout, stream=True)
    r.raise_for_status()
    filename = None
    cdisp = r.headers.get("content-disposition", "")
    m = re.search(r'filename="([^"]+)"', cdisp)
    if m:
        filename = m.group(1)
    if not filename:
        # fall back to file_id with extension from content-type
        ctype = r.headers.get("content-type", "")
        ext = ""
        if "wordprocessingml" in ctype:
            ext = ".docx"
        elif "pdf" in ctype:
            ext = ".pdf"
        filename = f"{file_id}{ext}"
    # sanitize filename
    filename = re.sub(r'[<>:"/\\\\|?*]', "_", filename)
    path = os.path.join(out_dir, filename)
    size = 0
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                size += len(chunk)
    return {
        "path": path,
        "filename": filename,
        "size_bytes": size,
        "content_type": r.headers.get("content-type", ""),
        "url": url,
    }


def assignments_overview(token: str, tenant_id: str, course_id: str = None) -> dict:
    """Unified read-only assignments view for a DP student.

    Merges (all GET):
      - EOL tests (/eol-tests/my/) — primary teacher-published assignments
      - Student assessments (/student/assessments/) — FA/SDL tasks with due dates
      - Shared resources (/resources/) — teacher materials (folders + files)
      - test-marks/me skipped for DP (PYP-only; returns BAD_REQUEST)
    Returns {eol, assessments, resources, course_id} with raw payloads so
    callers can render either JSON or a summary.
    """
    eol = eol_tests(token, tenant_id)
    assess = assessments(token)
    if course_id:
        res = list_resources(token, tenant_id, course_id=course_id, page_size=50)
    else:
        res = list_resources(token, tenant_id, page_size=20)
    return {"course_id": course_id, "eol": eol, "assessments": assess, "resources": res}


def summarize_assignments(overview: dict, limit_each: int = 15) -> str:
    """Human-readable unified assignments summary."""
    lines = []
    eol = overview.get("eol") or {}
    assess = overview.get("assessments") or {}
    res = overview.get("resources") or {}
    if isinstance(eol, dict):
        results = eol.get("results") or []
        lines.append(f"EOL tests: {eol.get('count', len(results))} total")
        for t in results[:limit_each]:
            lines.append(
                f"  [{t.get('status')}] {t.get('title')} ({t.get('subject')} — {t.get('topic')}) "
                f"score={t.get('score')}/{t.get('total_marks')} due={t.get('expires_message') or t.get('available_until')}"
            )
    if isinstance(assess, dict):
        results = assess.get("results") or []
        lines.append(f"Assessments: {assess.get('count', len(results))} total")
        for a in results[:limit_each]:
            inner = a.get("assessment") or {}
            lines.append(
                f"  [{a.get('status')}] {inner.get('title')} ({inner.get('subject')}) "
                f"due={inner.get('due_date')} teacher={inner.get('teacher_name')}"
            )
    if isinstance(res, dict):
        results = res.get("results") or []
        lines.append(f"Shared resources: {res.get('count', len(results))} total")
        for r in results[:limit_each]:
            kind = "FOLDER" if r.get("is_folder") else "FILE"
            lines.append(f"  [{kind}] {r.get('title')} by {r.get('teacher_name')}")
    lines.append("Note: test-marks/me is PYP-only (DP returns BAD_REQUEST) — use EOL + assessments.")
    return "\n".join(lines)


def progress_reports(token: str, tenant_id: str, student_id: str = None) -> dict:
    """Get progress report PDFs."""
    base = f"{API_BASE}/api/v2/report-engine/student-pdfs/"
    if student_id:
        url = f"{base}?student_id={student_id}"
    else:
        url = base
    return HTTP.get(url, headers=get_auth_headers(token), timeout=30).json()


def get_topic_content(token: str, unit_id: str) -> dict:
    """Get topic/unit content."""
    url = f"{API_BASE}/api/topic/unit/{unit_id}/"
    return HTTP.get(url, headers=get_auth_headers(token), timeout=15).json()


def raw_get(token: str, path: str, params: dict = None) -> dict:
    """Raw GET to any API path."""
    url = f"{API_BASE}{path}" if path.startswith("/") else path
    r = HTTP.get(url, headers=get_auth_headers(token), params=params, timeout=15)
    try:
        return r.json()
    except Exception:
        return {"status": r.status_code, "text": r.text[:2000]}


# --- Structured calls -------------------------------------------------------
#
# The helpers above return whatever JSON the LMS sends, errors included.
# Everything below goes through api(), which raises LMSError on a non-2xx
# reply so callers can tell `attempts_exceeded` from `past_due` from a
# dead token.


class LMSError(Exception):
    """Non-2xx reply from the LMS. `status` is the HTTP code, `body` the parsed reply."""

    def __init__(self, status: int, body: Any = None):
        self.status = status
        self.body = body
        self.code = body.get("code") if isinstance(body, dict) else None
        super().__init__(error_message(body) or f"Indus LMS answered HTTP {status}")


def error_message(body: Any) -> str:
    """Best human-readable message from an LMS error body (DRF and Indus shapes)."""
    if isinstance(body, str):
        return body.strip()[:300]
    if isinstance(body, list):
        return "; ".join(filter(None, (error_message(b) for b in body)))[:300]
    if not isinstance(body, dict):
        return ""
    for key in ("detail", "message", "error", "non_field_errors"):
        if body.get(key):
            return error_message(body[key])
    for key, value in body.items():
        if key in ("code", "status", "request_id", "timestamp", "details"):
            continue
        msg = error_message(value)
        if msg:
            return f"{key}: {msg}"
    return error_message(body.get("details"))


def api(token: str, method: str, path: str, *, json: Any = None, params: dict = None, timeout: int = 20):
    """One authenticated call. Returns parsed JSON ({} for an empty body); raises LMSError."""
    url = f"{API_BASE}{path}" if path.startswith("/") else path
    r = HTTP.request(method, url, headers=get_auth_headers(token), json=json, params=params, timeout=timeout)
    try:
        body = r.json() if r.content else {}
    except ValueError:
        body = {"text": r.text[:500]}
    if not r.ok:
        raise LMSError(r.status_code, body)
    return body


def _rows(data: Any) -> list:
    if isinstance(data, list):
        return data
    return (data.get("results") or []) if isinstance(data, dict) else []


def token_expiry(access: str) -> float:
    """`exp` of a JWT access token (0.0 when unreadable)."""
    try:
        payload = access.split(".")[1]
        return float(json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["exp"])
    except Exception:
        return 0.0


def ensure_fresh_token(margin: int = 300) -> Optional[dict]:
    """Load the saved token and refresh it before it expires.

    The rotated access/refresh pair is written back, so the CLI, the MCP
    server and exporters keep working after the browser-length access
    token lapses. Returns the token data (None when not logged in).
    """
    data = load_token()
    if not data or not data.get("access") or not data.get("refresh"):
        return data
    if token_expiry(data["access"]) - time.time() > margin:
        return data
    try:
        body = refresh_token(data["refresh"])
    except Exception:
        return data
    if isinstance(body, dict) and body.get("access"):
        data["access"] = body["access"]
        data["refresh"] = body.get("refresh", data["refresh"])
        save_token(data, quiet=True)
    return data


def session_context(margin: int = 300) -> tuple:
    """(access token, tenant id, user id) from the saved, freshly refreshed token."""
    data = ensure_fresh_token(margin)
    if not data or not data.get("access"):
        raise RuntimeError("No LMS token. Run `induslms login <email>` first.")
    user = data.get("user") or {}
    roles = user.get("roles") or []
    tenant = (roles[0].get("tenant_id") if roles else None) or os.environ.get("INDUSLMS_TENANT")
    if not tenant:
        raise RuntimeError("No tenant ID. Set INDUSLMS_TENANT or log in again.")
    return data["access"], tenant, user.get("id")


# --- More reads --------------------------------------------------------------


def assessments_all(token: str, assessment_type: str = None, course_id: str = None,
                    page_size: int = 100, max_pages: int = 25) -> list:
    """Every student assessment row (FA/SA), following pagination.

    Rows are `{assignment_id, status, marks, total_marks, submitted_at,
    student_submission_files, assessment: {id, title, due_date, questions,
    file_urls, submission_open, ...}}`. Detail calls take `assessment.id`.
    """
    items = []
    for page in range(1, max_pages + 1):
        params = {"page": page, "page_size": page_size}
        if assessment_type:
            params["assessment_type"] = assessment_type
        if course_id:
            params["course_id"] = course_id
        data = api(token, "GET", "/api/v1/student/assessments/", params=params)
        batch = _rows(data)
        items += batch
        if isinstance(data, list) or not batch or not data.get("next"):
            return items
    return items


def assessment_submission(token: str, assessment_id: str) -> dict:
    """What the student handed in: `{submission_urls, comment, submitted_at, status, answers}`."""
    return api(token, "GET", f"/api/v1/student/assessments/{assessment_id}/submission/")


def assessment_feedback(token: str, assessment_id: str) -> dict:
    """Teacher feedback: `{total_score, feedback_text, rubric_scores, annotated_files, final_remarks, has_feedback}`."""
    return api(token, "GET", f"/api/v1/student/assessments/{assessment_id}/feedback/")


def request_summary(token: str, assessment_ids: list) -> dict:
    """Extension/resubmission state per assessment id.

    Returns `{enabled, requests_max, reason_min_length, reason_max_length,
    items: {assessment_id: {can_request: {extension, resubmission},
    requests_used, requests_max, past_due, effective_due_date,
    resubmission_window_open, latest}}}`. Queried 50 ids at a time.
    """
    ids = list(dict.fromkeys(i for i in assessment_ids if i))
    out = None
    for start in range(0, max(len(ids), 1), 50):
        chunk = ids[start:start + 50]
        data = api(token, "GET", "/api/v1/student/requests/summary/",
                   params={"assessment_ids": ",".join(chunk)})
        out = data if out is None else {**out, "items": {**(out.get("items") or {}), **(data.get("items") or {})}}
        if not data.get("enabled"):
            break
    return out or {"enabled": False, "items": {}}


def eol_result(token: str, tenant_id: str, test_id: str, user_id: str) -> dict:
    """A submitted EOL test: score plus every response with the correct option and AI note.

    `test_id` is the test uuid (`id` in eol_tests rows), not the short id.
    """
    return api(token, "GET", f"/api/v1/tenants/{tenant_id}/eol-tests/{test_id}/students/{user_id}/")


def eol_feedback(token: str, tenant_id: str, test_id: str) -> list:
    """Teacher feedback notes on one EOL test."""
    data = api(token, "GET", f"/api/v1/tenants/{tenant_id}/eol-tests/{test_id}/feedback/")
    return data.get("feedbacks", []) if isinstance(data, dict) else _rows(data)


def learning_tasks(token: str, tenant_id: str, course_id: str = None) -> list:
    """Learning tasks (`/studentassignment` in the web app): `{id, title, instructions,
    due_date, status, score, grade, feedback_text, attachments[{name, file_url, ...}]}`."""
    params = {"course_id": course_id} if course_id else None
    return _rows(api(token, "GET", f"/api/v1/tenants/{tenant_id}/assignments/student/list/", params=params))


def learning_task_detail(token: str, tenant_id: str, task_id: str) -> dict:
    """`{assignment, recipient_status, submission, score, grade, feedback_text}` for one task."""
    return api(token, "GET", f"/api/v1/tenants/{tenant_id}/assignments/student/{task_id}/detail/")


def announcements_visible(token: str, academic_year: str = None) -> list:
    """Announcements visible to the student, with the full HTML `message`, `creator`
    and `file_urls` (the plain /api/announcements/ list is the older endpoint)."""
    params = {"academic_year": academic_year} if academic_year else None
    return _rows(api(token, "GET", "/api/announcements/visible/", params=params))


def message_contacts(token: str, tenant_id: str) -> list:
    """People the student may message: `{user_id, full_name, role, email, subjects, subject_label}`."""
    return _rows(api(token, "GET", f"/api/v1/tenants/{tenant_id}/messages/contacts/"))


def message_threads(token: str, tenant_id: str) -> list:
    """Conversations: `{contact_user_id, contact_user_name, contact_user_role, last_message, last_updated, status}`."""
    return _rows(api(token, "GET", f"/api/v1/tenants/{tenant_id}/messages/threads/"))


def message_conversation(token: str, tenant_id: str, user_id: str, page: int = None) -> dict:
    """Messages with one contact, oldest first.

    The LMS pages newest first; results are reversed here, as the web app does.
    Each message: `{id, from_user_id, from_user_name, to_user_id, text, sent_at, read_at, status}`.
    """
    data = api(token, "GET", f"/api/v1/tenants/{tenant_id}/messages/conversation/{user_id}/",
               params={"page": page} if page else None)
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        data = {**data, "results": list(reversed(data["results"]))}
    return data


def program_years(token: str, tenant_id: str, active: bool = True) -> list:
    """Programme years (`program_year_id`, `program_type`, `academic_year`) for the school."""
    params = {"tenant_id": tenant_id}
    if active:
        params["is_active"] = "true"
    return _rows(api(token, "GET", "/api/v1/programs/year-list/", params=params))


def policies(token: str, tenant_id: str, program_year_id: str = None) -> list:
    """School policy PDFs `{title, description, file_url, version, status}`.

    Without `program_year_id`, every active programme year is read and
    duplicates are dropped by title, like the web app.
    """
    years = [program_year_id] if program_year_id else [y.get("program_year_id") for y in program_years(token, tenant_id)]
    seen, out = set(), []
    for year in filter(None, years):
        for p in _rows(api(token, "GET", f"/api/v1/tenants/{tenant_id}/academic-years/{year}/policies/")):
            key = (p.get("title") or "").strip().lower()
            if key and key in seen:
                continue
            seen.add(key)
            out.append(p)
    return out


def help_articles(token: str, tenant_id: str, audience: str = "student") -> list:
    """Help articles published for students (often empty)."""
    return _rows(api(token, "GET", f"/api/v1/tenants/{tenant_id}/help/", params={"audience": audience}))


# --- Writes ------------------------------------------------------------------
#
# Each of these changes school data. None retries itself: a failed submit
# is reported, never re-sent.


def _options(answers) -> list:
    """Normalise EOL answers to [{question_id, selected_option}] with a-d options."""
    pairs = answers.items() if isinstance(answers, dict) else (
        (a.get("question_id"), a.get("selected_option")) for a in answers)
    out = []
    for qid, opt in pairs:
        opt = str(opt or "").strip().lower()
        if not qid or opt not in ("a", "b", "c", "d"):
            raise ValueError(f"Answer for question {qid!r} must be one of a, b, c, d.")
        out.append({"question_id": qid, "selected_option": opt})
    return out


def eol_open(token: str, tenant_id: str, short_id: str, passcode: str) -> dict:
    """WRITE (starts an attempt). Open an EOL test with its passcode.

    Takes the short id (e.g. "ECO082"). Returns `{id (uuid), title,
    total_marks, questions[{id, question_text, option_a_text..option_d_text,
    *_image_url, marks}], already_submitted}`.
    """
    return api(token, "POST", f"/api/v1/tenants/{tenant_id}/eol-tests/open/",
               json={"test_id": short_id.strip(), "passcode": passcode.strip()})


def eol_submit(token: str, tenant_id: str, test_uuid: str, passcode: str, answers) -> dict:
    """WRITE. Submit an opened EOL test. `answers` is {question_id: "a".."d"} or a list.

    Uses the uuid from eol_open() and re-sends the passcode. Returns
    `{id (submission), score, total_marks, percent, submitted_at}`.
    """
    return api(token, "POST", f"/api/v1/tenants/{tenant_id}/eol-tests/{test_uuid}/submit/",
               json={"test_id": test_uuid, "passcode": passcode.strip(), "answers": _options(answers)})


def eol_proctor_event(token: str, tenant_id: str, test_uuid: str,
                      event_type: str = "document_visibility_hidden") -> dict:
    """WRITE. Report a proctoring event (the web app sends one each time the tab is hidden mid-test).

    Returns `{proctor_violation_count, suspend_threshold, proctor_suspended}`.
    """
    return api(token, "POST", f"/api/v1/tenants/{tenant_id}/eol-tests/{test_uuid}/proctoring/",
               json={"event_type": event_type})


def eol_explain(token: str, tenant_id: str, test_id: str, user_id: str, *, submission_id: str,
                question_id: str, question_text: str, options: dict, selected_option: str,
                correct_option: str, is_correct: bool) -> dict:
    """Ask for the AI learning note on one answered question: `{explanation, cached}`.

    `options` is {"a": text, ...}. Generates content server-side but
    does not touch the score.
    """
    body = {"submission_id": submission_id, "question_id": question_id, "question_text": question_text,
            "options": options, "selected_option": selected_option, "correct_option": correct_option,
            "is_correct": bool(is_correct)}
    return api(token, "POST", f"/api/v1/tenants/{tenant_id}/eol-tests/{test_id}/students/{user_id}/question-explanations/",
               json=body, timeout=60)


def upload_file(token: str, tenant_id: str, module: str, entity_id: str, filename: str,
                data: bytes, content_type: str = None) -> dict:
    """Upload bytes to the LMS's S3 bucket via a presigned URL.

    Returns `{file_url, name, content_type, size_bytes}`. Use
    TASK_UPLOAD_MODULE for learning tasks and ASSESSMENT_UPLOAD_MODULE for FA/SA.
    """
    ctype = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    slot = api(token, "POST", "/api/v1/s3uploads/get-upload-url/", json={
        "tenant_id": tenant_id, "module": module, "entity_id": entity_id,
        "filename": filename, "content_type": ctype})
    if not slot.get("upload_url") or not slot.get("file_url"):
        raise LMSError(502, {"message": "Indus LMS gave an invalid upload URL."})
    r = HTTP.request((slot.get("method") or "PUT").upper(), slot["upload_url"], data=data,
                     headers={"Content-Type": ctype}, timeout=300)
    if not r.ok:
        raise LMSError(r.status_code, {"message": f"Uploading {filename} failed."})
    return {"file_url": slot["file_url"], "name": filename, "content_type": ctype, "size_bytes": len(data)}


def upload_files(token: str, tenant_id: str, module: str, files: list) -> list:
    """Upload [(filename, bytes, content_type)] under one new entity id; all or nothing."""
    entity = str(uuid.uuid4())
    return [upload_file(token, tenant_id, module, entity, name, data, ctype) for name, data, ctype in files]


def task_submit(token: str, tenant_id: str, task_id: str, files: list, text: str = "") -> dict:
    """WRITE. Hand in a learning task. `files` are upload_file() results (at least one)."""
    if not files:
        raise ValueError("Attach at least one file.")
    return api(token, "POST", f"/api/v1/tenants/{tenant_id}/assignments/student/{task_id}/submit/",
               json={"submission_text": text or "", "submission_files": files})


def assessment_submit_questions(token: str, assessment_id: str, responses: list,
                                submission_urls: list = (), comment: str = "") -> dict:
    """WRITE. Submit an FA/SA that has questions.

    `responses` is [{question_id, selected_option}] for MCQ or
    [{question_id, answer_text}] for written answers.
    """
    return api(token, "POST", f"/api/v1/student/assessments/{assessment_id}/submit-questions/",
               json={"responses": list(responses), "submission_urls": list(submission_urls), "comment": comment or ""})


def assessment_submit_upload(token: str, assessment_id: str, submission_urls: list, comment: str = "") -> dict:
    """WRITE. Submit an FA/SA as uploaded files (`submission_urls` are file_url strings)."""
    return api(token, "POST", f"/api/v1/student/assessments/{assessment_id}/submit-upload/",
               json={"submission_urls": list(submission_urls), "comment": comment or "", "assessment_id": assessment_id})


def assessment_resubmit(token: str, assessment_id: str, keep_indexes: list, new_files: list,
                        comment: str = None, base_submitted_at: str = None) -> dict:
    """WRITE. Resubmit inside an open resubmission window, keeping some earlier files."""
    body = {"keep_indexes": list(keep_indexes), "new_files": list(new_files)}
    if base_submitted_at:
        body["base_submitted_at"] = base_submitted_at
    if comment is not None:
        body["comment"] = comment
    return api(token, "POST", f"/api/v1/student/assessments/{assessment_id}/resubmit/", json=body)


def assessment_request(token: str, assessment_id: str, request_type: str, reason: str,
                       preferred_due_at: str = None) -> dict:
    """WRITE. Ask the teacher for an "extension" or a "resubmission" (reason: 10-500 chars)."""
    if request_type not in ("extension", "resubmission"):
        raise ValueError("request_type must be 'extension' or 'resubmission'.")
    body = {"request_type": request_type, "reason": reason.strip()}
    if preferred_due_at:
        body["preferred_due_at"] = preferred_due_at
    return api(token, "POST", f"/api/v1/student/assessments/{assessment_id}/requests/", json=body)


def request_cancel(token: str, request_id: str) -> dict:
    """WRITE. Withdraw a pending extension/resubmission request."""
    return api(token, "POST", f"/api/v1/student/requests/{request_id}/cancel/")


def send_message(token: str, tenant_id: str, to_user_id: str, text: str) -> dict:
    """WRITE. Send a message to a teacher (see message_contacts()). Returns the stored message."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Message is empty.")
    return api(token, "POST", f"/api/v1/tenants/{tenant_id}/messages/", json={"to_user_id": to_user_id, "text": text})


def notification_read(token: str, tenant_id: str, notification_id: str) -> dict:
    """WRITE. Mark one notification read."""
    return api(token, "POST", f"/api/v1/tenants/{tenant_id}/notifications/{notification_id}/read/")


def notifications_read_all(token: str, tenant_id: str) -> dict:
    """WRITE. Mark every notification read."""
    return api(token, "POST", f"/api/v1/tenants/{tenant_id}/notifications/read-all/")


def announcement_read(token: str, announcement_id: str) -> dict:
    """WRITE. Record that the student opened an announcement (`{recorded: true}`)."""
    return api(token, "POST", f"/api/announcements/{announcement_id}/read/")


def pp(data):
    print(json.dumps(data, indent=2, default=str))


def doctor() -> dict:
    """Check install health: deps, token, tenant, platform extras. Never raises."""
    import shutil
    import platform

    result: dict = {
        "ok": True,
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "token_file": TOKEN_FILE,
        "checks": {},
    }
    checks = result["checks"]

    try:
        import mcp  # noqa: F401

        checks["mcp"] = "ok"
    except Exception as e:
        checks["mcp"] = f"missing: {e}"
        result["ok"] = False

    try:
        import msal  # noqa: F401

        checks["msal"] = "ok"
    except Exception as e:
        checks["msal"] = f"missing: {e}"

    token_data = ensure_fresh_token()
    if not token_data or not token_data.get("access"):
        checks["lms_token"] = f"missing (run: python3 lms.py login <email>; file={TOKEN_FILE})"
        result["ok"] = False
    else:
        checks["lms_token"] = "ok"
        try:
            data = me(token_data["access"])
            if isinstance(data, dict) and (data.get("email") or data.get("id")):
                checks["lms_api"] = "ok"
            else:
                checks["lms_api"] = f"warn: unexpected profile response {str(data)[:120]}"
        except Exception as e:
            checks["lms_api"] = f"fail: {e}"
            result["ok"] = False
        roles = (token_data.get("user") or {}).get("roles") or []
        tenant = roles[0].get("tenant_id") if roles else os.environ.get("INDUSLMS_TENANT")
        checks["tenant"] = "ok" if tenant else "missing (set INDUSLMS_TENANT or re-login)"

    if not os.environ.get("INDUS_OUTLOOK_CLIENT_ID"):
        checks["outlook"] = "unconfigured (outlook_* disabled; set INDUS_OUTLOOK_CLIENT_ID + run outlook.py login)"
    else:
        checks["outlook"] = "configured"

    if shutil.which("osascript") is None:
        checks["schoolmail"] = "unavailable (macOS Mail.app only; schoolmail_* disabled on this platform)"
    else:
        checks["schoolmail"] = "ok"

    return result


def _parse_flags(raw_args):
    """Split CLI args into positionals and --flag values. Supports:
    --json, --unread-only, --inline, --yes, --all, --course X, --parent X,
    --page N, --page-size N, --limit N, --offset N, --out DIR, --type T,
    --year Y, --comment C, --text T, --due ISO."""
    pos, flags = [], {}
    i = 0
    while i < len(raw_args):
        a = raw_args[i]
        if a == "--json":
            flags["json"] = True
        elif a == "--unread-only":
            flags["unread_only"] = True
        elif a == "--inline":
            flags["inline"] = True
        elif a in ("--yes", "-y"):
            flags["yes"] = True
        elif a == "--all":
            flags["all"] = True
        elif a in ("--course", "--parent", "--page", "--page-size", "--limit", "--offset", "--out",
                   "--type", "--year", "--comment", "--text", "--due") and i + 1 < len(raw_args):
            flags[a[2:].replace("-", "_")] = raw_args[i + 1]
            i += 1
        else:
            pos.append(a)
        i += 1
    return pos, flags


def _need(pos: list, n: int, usage: str) -> None:
    if len(pos) < n:
        raise ValueError(f"Usage: {usage}")


def _confirm(question: str, flags: dict) -> bool:
    if flags.get("yes"):
        return True
    if not sys.stdin.isatty():
        raise ValueError("Not sending without --yes (no terminal to confirm on).")
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def _read_files(paths: list) -> list:
    out = []
    for p in paths:
        with open(os.path.expanduser(p), "rb") as f:
            out.append((os.path.basename(p), f.read(), None))
    return out


def _cmd_tasks(token, tid, uid, pos, flags):
    rows = learning_tasks(token, tid, flags.get("course"))
    if flags.get("json"):
        return pp(rows)
    for t in rows:
        print(f"  [{t.get('status')}] {t.get('title')} ({t.get('subject')}) due={t.get('due_date')} id={t.get('id')}")
    print(f"{len(rows)} learning task(s)")


def _cmd_rows(fn, fmt):
    def run(token, tid, uid, pos, flags):
        rows = fn(token, tid)
        if flags.get("json"):
            return pp(rows)
        for r in rows:
            print("  " + fmt(r))
        print(f"{len(rows)} item(s)")
    return run


def _cmd_eol_take(token, tid, uid, pos, flags):
    import getpass

    _need(pos, 1, "eol-take <SHORT_ID>")
    short_id = pos[0].strip()
    passcode = getpass.getpass(f"Passcode for {short_id}: ")
    if not _confirm(f"Open {short_id} now? This starts your attempt.", flags):
        return print("Not opened.")
    test = eol_open(token, tid, short_id, passcode)
    if test.get("already_submitted"):
        return print("You have already submitted this test.")
    questions = test.get("questions") or []
    print(f"\n{test.get('title')} — {len(questions)} question(s), {test.get('total_marks')} marks\n")
    answers = {}
    try:
        for n, q in enumerate(questions, 1):
            print(f"Question {n} of {len(questions)}: {q.get('question_text')}")
            for opt in "abcd":
                if q.get(f"option_{opt}_text"):
                    print(f"   {opt}) {q[f'option_{opt}_text']}")
            while answers.get(q["id"]) not in tuple("abcd"):
                answers[q["id"]] = input("Your answer (a-d): ").strip().lower()
            print()
    except (KeyboardInterrupt, EOFError):
        print("\nLeft without submitting. The web app counts this as a mid-test exit.")
        return
    if not _confirm(f"Submit {len(answers)} answer(s)? You cannot change them afterwards.", flags):
        return print("Not submitted. The web app counts this as a mid-test exit.")
    result = eol_submit(token, tid, test["id"], passcode, answers)
    print(f"Submitted: {result.get('score')}/{result.get('total_marks')} ({result.get('percent')}%)")


def _cmd_fa_submit(token, tid, uid, pos, flags):
    _need(pos, 2, "fa-submit <assessment_id> <file>... [--comment C]")
    files = _read_files(pos[1:])
    if not _confirm(f"Hand in {len(files)} file(s) for assessment {pos[0]}?", flags):
        return print("Not submitted.")
    urls = [f["file_url"] for f in upload_files(token, tid, ASSESSMENT_UPLOAD_MODULE, files)]
    pp(assessment_submit_upload(token, pos[0], urls, flags.get("comment") or ""))


def _cmd_fa_request(token, tid, uid, pos, flags):
    _need(pos, 3, "fa-request <assessment_id> extension|resubmission <reason...> [--due ISO]")
    reason = " ".join(pos[2:])
    if not _confirm(f"Send a {pos[1]} request to the teacher?", flags):
        return print("Not sent.")
    pp(assessment_request(token, pos[0], pos[1], reason, flags.get("due")))


def _cmd_task_submit(token, tid, uid, pos, flags):
    _need(pos, 2, "task-submit <task_id> <file>... [--text T]")
    files = _read_files(pos[1:])
    if not _confirm(f"Hand in {len(files)} file(s) for task {pos[0]}?", flags):
        return print("Not submitted.")
    pp(task_submit(token, tid, pos[0], upload_files(token, tid, TASK_UPLOAD_MODULE, files), flags.get("text") or ""))


def _cmd_send(token, tid, uid, pos, flags):
    _need(pos, 2, "send <user_id> <text...>")
    text = " ".join(pos[1:])
    if not _confirm(f"Send this message?\n  {text}\n", flags):
        return print("Not sent.")
    pp(send_message(token, tid, pos[0], text))


def _one(usage, fn):
    def run(token, tid, uid, pos, flags):
        _need(pos, 1, usage)
        pp(fn(token, tid, uid, pos[0]))
    return run


_DETAIL_COMMANDS = {
    "fa-submission": _one("fa-submission <assessment_id>", lambda t, tid, uid, a: assessment_submission(t, a)),
    "fa-feedback": _one("fa-feedback <assessment_id>", lambda t, tid, uid, a: assessment_feedback(t, a)),
    "fa-requests": _one("fa-requests <assessment_id>[,...]", lambda t, tid, uid, a: request_summary(t, a.split(","))),
    "eol-result": _one("eol-result <test_uuid>", lambda t, tid, uid, a: eol_result(t, tid, a, uid)),
    "eol-feedback": _one("eol-feedback <test_uuid>", lambda t, tid, uid, a: eol_feedback(t, tid, a)),
    "task": _one("task <task_id>", lambda t, tid, uid, a: learning_task_detail(t, tid, a)),
    "conversation": _one("conversation <user_id>", lambda t, tid, uid, a: message_conversation(t, tid, a)),
    "tasks": _cmd_tasks,
    "announcements-visible": lambda t, tid, uid, pos, flags: pp(announcements_visible(t, pos[0] if pos else flags.get("year"))),
    "contacts": _cmd_rows(message_contacts, lambda r: f"{r.get('full_name')} ({r.get('role')}, {r.get('subject_label') or ''}) id={r.get('user_id')}"),
    "threads": _cmd_rows(message_threads, lambda r: f"{r.get('contact_user_name')}: {(r.get('last_message') or '')[:70]} id={r.get('contact_user_id')}"),
    "years": _cmd_rows(program_years, lambda r: f"{r.get('program_type')} {r.get('academic_year')} id={r.get('program_year_id')}"),
    "policies": _cmd_rows(policies, lambda r: f"{r.get('title')} v{r.get('version')} {r.get('file_url')}"),
    "help-articles": _cmd_rows(help_articles, lambda r: f"{r.get('title')}"),
}

_WRITE_COMMANDS = {
    "eol-take": _cmd_eol_take,
    "fa-submit": _cmd_fa_submit,
    "fa-request": _cmd_fa_request,
    "request-cancel": _one("request-cancel <request_id>", lambda t, tid, uid, a: request_cancel(t, a)),
    "task-submit": _cmd_task_submit,
    "send": _cmd_send,
    "notification-read": _one("notification-read <id>", lambda t, tid, uid, a: notification_read(t, tid, a)),
    "notifications-read-all": lambda t, tid, uid, pos, flags: pp(notifications_read_all(t, tid)),
    "announcement-read": _one("announcement-read <id>", lambda t, tid, uid, a: announcement_read(t, a)),
}


def main():
    args = sys.argv[1:]

    if not args:
        print("""
IndusLMS Agent CLI

The access token is refreshed automatically before it expires. Commands
marked WRITE change school data and ask before sending (--yes skips that).

Core:
  login <email> <password>                Login and save token
  doctor                                   Check install health (deps, token, tenant, extras)
  me                                       Show my profile
  profile                                  Show detailed profile
  courses [tenant_id] [year]               My courses
  attendance [--json]                      Attendance summary + records
  attendance-day [tenant_id] [--json]      Day-wise attendance breakdown
  notifications [tenant_id] [limit] [offset] [--unread-only] [--json]
                                           View notifications (no mark-read)
  announcements [tenant] [year]            School announcements
  calendar                                 Calendar events

Assignments (teacher-published work):
  assessments [--json]                     FA/SDL assessments with due dates
  eol-tests [tenant_id] [--limit N] [--offset N] [--json]
                                           End-of-lesson tests
  marks <tenant_id> <course_id>            PYP test-marks (DP returns error)
  dp [tenant_id] [project_id] [section]    DP projects (ee/tok/cas/exhibition/...)
  assignments [tenant_id] [--course CID] [--json]
                                           Unified EOL + assessments + resources

Shared resources:
  resources [tenant_id] [--course CID] [--parent RID] [--page N] [--page-size N] [--json]
                                           List folders/files from teachers
  children [tenant_id] <resource_id> [--json]
                                           List children of a folder
  resource [tenant_id] <resource_id> [--json]
                                           Show one resource's metadata
  download [tenant_id] <resource_id> <file_id> [--out DIR] [--inline]
                                           Download a shared file (default ~/Downloads/induslms)

  reports <tenant_id> [student_id]         Progress report PDFs
  get <path>                               Raw GET to any API path

Detail views:
  assessments --all [--type FA|SA] [--course CID] [--json]
                                           Every FA/SA row, all pages
  fa-submission <assessment_id>            What you handed in
  fa-feedback <assessment_id>              Teacher feedback and rubric scores
  fa-requests <assessment_id>[,...]        Extension/resubmission status
  eol-tests ... [--course CID] [--year 2026-27]
  eol-result <test_uuid>                   Your answers vs the correct ones
  eol-feedback <test_uuid>                 Teacher feedback on a test
  tasks [--course CID] [--json]            Learning tasks
  task <task_id>                           One learning task with your submission
  announcements-visible [year] [--json]    Full announcements (HTML, attachments)
  contacts | threads                       Messaging contacts / conversations
  conversation <user_id>                   Messages with one person, oldest first
  years | policies | help-articles         Programme years, school policies, help

Writes:
  eol-take <SHORT_ID>                      WRITE: take an EOL test (passcode, answers, submit)
  fa-submit <assessment_id> <file>... [--comment C]
                                           WRITE: hand in an FA/SA as files
  fa-request <assessment_id> extension|resubmission <reason...> [--due ISO]
                                           WRITE: ask for an extension/resubmission
  request-cancel <request_id>              WRITE: withdraw a pending request
  task-submit <task_id> <file>... [--text T]
                                           WRITE: hand in a learning task
  send <user_id> <text...>                 WRITE: message a teacher
  notification-read <id> | notifications-read-all
                                           WRITE: mark notifications read
  announcement-read <id>                   WRITE: record an announcement as read

Environment (.env supported via python-dotenv):
  INDUSLMS_EMAIL       email
  INDUSLMS_PASS        password
  INDUSLMS_TENANT      tenant ID
  INDUSLMS_TOKEN_FILE  token path (default ~/.induslms_token.json)
""")
        return

    cmd = args[0]
    if cmd in ("doctor", "status", "check"):
        _, flags = _parse_flags(args[1:])
        result = doctor()
        if flags.get("json"):
            pp(result)
        else:
            print("induslms doctor: " + ("OK" if result["ok"] else "ISSUES FOUND"))
            print(f"  python={result['python']} platform={result['platform']}")
            print(f"  token_file={result['token_file']}")
            for k, v in result["checks"].items():
                print(f"  {k}: {v}")
            if not result["ok"]:
                print("\nFix: python3 lms.py login <email> (see README Quickstart)")
        return

    token_data = load_token() if cmd == "login" else ensure_fresh_token()
    token = token_data.get("access") if token_data else None
    tenant_id = token_data.get("user", {}).get("roles", [{}])[0].get("tenant_id") if token_data else None

    if cmd == "login":
        email = args[1] if len(args) > 1 else os.environ.get("INDUSLMS_EMAIL") or input("Email: ")
        password = args[2] if len(args) > 2 else os.environ.get("INDUSLMS_PASS") or input("Password: ")
        data = login(email, password)
        pp(data)

    elif cmd == "me":
        if not token:
            print("No token. Run login first.")
            return
        pp(me(token))

    elif cmd == "profile":
        if not token:
            print("No token. Run login first.")
            return
        pp(profile(token))

    elif cmd == "courses":
        if not token:
            print("No token. Run login first.")
            return
        tid = args[1] if len(args) > 1 else (tenant_id or os.environ.get("INDUSLMS_TENANT") or input("Tenant ID: "))
        year = args[2] if len(args) > 2 else None
        pp(my_courses(token, tid, year))

    elif cmd == "attendance":
        if not token:
            print("No token. Run login first.")
            return
        _, flags = _parse_flags(args[1:])
        data = attendance(token)
        if flags.get("json"):
            pp(data)
        else:
            print(summarize_attendance(data))
            print("\n(--json for raw payload; attendance-day for day breakdown)")

    elif cmd == "attendance-day":
        if not token:
            print("No token. Run login first.")
            return
        pos, flags = _parse_flags(args[1:])
        tid = pos[0] if pos else (tenant_id or os.environ.get("INDUSLMS_TENANT") or input("Tenant ID: "))
        data = attendance_day(token, tid)
        if flags.get("json"):
            pp(data)
        else:
            pp(data) if isinstance(data, list) else print(summarize_attendance(attendance(token), data))

    elif cmd == "notifications":
        if not token:
            print("No token. Run login first.")
            return
        pos, flags = _parse_flags(args[1:])
        tid = pos[0] if pos else (tenant_id or os.environ.get("INDUSLMS_TENANT") or input("Tenant ID: "))
        limit = int(flags.get("limit") or (pos[1] if len(pos) > 1 else 20))
        offset = int(flags.get("offset") or (pos[2] if len(pos) > 2 else 0))
        data = notifications(token, tid, limit=limit, offset=offset,
                             unread_only=bool(flags.get("unread_only")))
        if flags.get("json"):
            pp(data)
        else:
            print(summarize_notifications(data))
            print("\n(--json for raw payload. Read-only: no mark-read calls.)")

    elif cmd == "announcements":
        if not token:
            print("No token. Run login first.")
            return
        tenant = args[1] if len(args) > 1 else None
        year = args[2] if len(args) > 2 else None
        pp(announcements(token, tenant, year))

    elif cmd == "calendar":
        if not token:
            print("No token. Run login first.")
            return
        pp(calendar_events(token))

    elif cmd == "assessments":
        if not token:
            print("No token. Run login first.")
            return
        _, flags = _parse_flags(args[1:])
        if flags.get("all") or flags.get("type") or flags.get("course"):
            pp(assessments_all(token, flags.get("type"), flags.get("course")))
        else:
            pp(assessments(token))

    elif cmd == "eol-tests":
        if not token:
            print("No token. Run login first.")
            return
        pos, flags = _parse_flags(args[1:])
        tid = pos[0] if pos else (tenant_id or os.environ.get("INDUSLMS_TENANT") or input("Tenant ID: "))
        limit = int(flags["limit"]) if flags.get("limit") else None
        offset = int(flags.get("offset") or 0)
        pp(eol_tests(token, tid, limit=limit, offset=offset,
                     course_id=flags.get("course"), year=flags.get("year")))

    elif cmd == "marks":
        if not token:
            print("No token. Run login first.")
            return
        pos, _ = _parse_flags(args[1:])
        if len(pos) < 1:
            print("Usage: marks <tenant_id> <course_id>  (PYP only; DP returns BAD_REQUEST)")
            return
        tid = pos[0] if len(pos) > 0 else tenant_id
        cid = pos[1] if len(pos) > 1 else None
        if not cid:
            print("Usage: marks <tenant_id> <course_id>")
            return
        pp(test_marks_me(token, tid, cid))

    elif cmd == "dp":
        if not token:
            print("No token. Run login first.")
            return
        pos, _ = _parse_flags(args[1:])
        tid = pos[0] if len(pos) > 0 else (tenant_id or os.environ.get("INDUSLMS_TENANT"))
        if not tid:
            print("Usage: dp [tenant_id] [project_id] [section e.g. ee/essay|tok|cas|exhibition]")
            return
        if len(pos) < 2:
            pp(dp_projects(token, tid))
        elif len(pos) < 3:
            print("Usage: dp <tenant_id> <project_id> <section>  (e.g. dp TID PID ee/essay)")
            print("Sections: ee, ee/essay, ee/plan, ee/proposal, ee/rpf, ee/rrs, tok, tok/essay, cas, exhibition, reflective-project/assessment, ...")
            return
        else:
            pp(dp_student_section(token, tid, pos[1], pos[2]))

    elif cmd == "assignments":
        if not token:
            print("No token. Run login first.")
            return
        pos, flags = _parse_flags(args[1:])
        tid = pos[0] if pos else (tenant_id or os.environ.get("INDUSLMS_TENANT") or input("Tenant ID: "))
        overview = assignments_overview(token, tid, course_id=flags.get("course"))
        if flags.get("json"):
            pp(overview)
        else:
            print(summarize_assignments(overview))

    elif cmd == "resources":
        if not token:
            print("No token. Run login first.")
            return
        pos, flags = _parse_flags(args[1:])
        tid = pos[0] if pos else (tenant_id or os.environ.get("INDUSLMS_TENANT") or input("Tenant ID: "))
        data = list_resources(
            token, tid,
            course_id=flags.get("course"),
            parent_resource_id=flags.get("parent"),
            page=int(flags.get("page") or 1),
            page_size=int(flags.get("page_size") or 20),
        )
        if flags.get("json"):
            pp(data)
        else:
            print(summarize_resources(data))
            print("\n(children <resource_id> to open a FOLDER; download <rid> <fid> to save a file; --json for raw)")

    elif cmd == "children":
        if not token:
            print("No token. Run login first.")
            return
        pos, flags = _parse_flags(args[1:])
        if len(pos) < 1:
            print("Usage: children [tenant_id] <resource_id>")
            return
        if len(pos) == 1:
            tid, rid = (tenant_id or os.environ.get("INDUSLMS_TENANT")), pos[0]
        else:
            tid, rid = pos[0], pos[1]
        data = list_resources(token, tid, parent_resource_id=rid, page_size=50)
        if flags.get("json"):
            pp(data)
        else:
            print(summarize_resources(data))

    elif cmd == "resource":
        if not token:
            print("No token. Run login first.")
            return
        pos, flags = _parse_flags(args[1:])
        if len(pos) < 1:
            print("Usage: resource [tenant_id] <resource_id>")
            return
        if len(pos) == 1:
            tid, rid = (tenant_id or os.environ.get("INDUSLMS_TENANT")), pos[0]
        else:
            tid, rid = pos[0], pos[1]
        data = get_resource(token, tid, rid)
        if flags.get("json"):
            pp(data)
        else:
            pp(data)
            if isinstance(data, dict) and data.get("is_folder") and data.get("child_count"):
                print(f"\n(Folder with {data.get('child_count')} children — run: children {rid})")
            if isinstance(data, dict) and data.get("file_urls"):
                print("Files:")
                for f in data["file_urls"]:
                    print(f"  {f.get('name')} (file_id={f.get('file_id') or f.get('id')})")

    elif cmd == "download":
        if not token:
            print("No token. Run login first.")
            return
        pos, flags = _parse_flags(args[1:])
        # download [tid] <rid> <fid>  (tid optional if token has it)
        if len(pos) == 2:
            tid, rid, fid = (tenant_id or os.environ.get("INDUSLMS_TENANT")), pos[0], pos[1]
        elif len(pos) >= 3:
            tid, rid, fid = pos[0], pos[1], pos[2]
        else:
            print("Usage: download [tenant_id] <resource_id> <file_id> [--out DIR] [--inline]")
            return
        try:
            result = download_resource_file(
                token, tid, rid, fid,
                out_dir=flags.get("out"),
                disposition="inline" if flags.get("inline") else "attachment",
            )
            print(f"[+] Saved {result['filename']} ({result['size_bytes']} bytes, {result['content_type']})")
            print(f"    -> {result['path']}")
        except Exception as e:
            print(f"Download failed: {e}")
            sys.exit(1)

    elif cmd == "reports":
        if not token:
            print("No token. Run login first.")
            return
        tid = args[1] if len(args) > 1 else (tenant_id or os.environ.get("INDUSLMS_TENANT") or input("Tenant ID: "))
        student_id = args[2] if len(args) > 2 else None
        pp(progress_reports(token, tid, student_id))

    elif cmd == "get":
        if not token:
            print("No token. Run login first.")
            return
        path = args[1]
        pp(raw_get(token, path))

    elif cmd in _DETAIL_COMMANDS or cmd in _WRITE_COMMANDS:
        if not token:
            print("No token. Run login first.")
            return
        user_id = (token_data.get("user") or {}).get("id")
        tid = tenant_id or os.environ.get("INDUSLMS_TENANT")
        pos, flags = _parse_flags(args[1:])
        try:
            (_DETAIL_COMMANDS.get(cmd) or _WRITE_COMMANDS[cmd])(token, tid, user_id, pos, flags)
        except LMSError as e:
            print(f"Indus LMS refused ({e.status}): {e}")
            sys.exit(1)
        except ValueError as e:
            print(str(e))
            sys.exit(2)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()