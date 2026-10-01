#!/usr/bin/env python3
"""
IndusLMS Agent Tool
API Base: https://api.induslms.com
Auth: JWT Bearer tokens from /api/v1/auth/login/
"""

import requests
import json
import sys
import os
from typing import Optional, Dict, Any

API_BASE = "https://api.induslms.com"
TOKEN_FILE = os.path.expanduser("~/.induslms_token.json")

HEADERS_BASE = {
    "Content-Type": "application/json",
    "Origin": "https://induslms.com",
    "Referer": "https://induslms.com/",
}


def save_token(data: dict):
    """Save token data to file."""
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)
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
    r = requests.post(url, json=payload, headers=headers, timeout=15)
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
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    return r.json()


def me(token: str) -> dict:
    """Get current user profile."""
    url = f"{API_BASE}/api/v1/auth/me/"
    return requests.get(url, headers=get_auth_headers(token), timeout=15).json()


def profile(token: str) -> dict:
    """Get detailed profile."""
    url = f"{API_BASE}/api/v1/profile/me/"
    return requests.get(url, headers=get_auth_headers(token), timeout=15).json()


def my_courses(token: str, tenant_id: str, year: str = None, include_classes=True) -> dict:
    """Get student courses for a tenant."""
    params = []
    if year:
        params.append(f"year={year}")
    params.append(f"include_classes={str(include_classes).lower()}")
    params.append("include_teachers=true")
    param_str = "&".join(params)
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/me/student/courses?{param_str}"
    return requests.get(url, headers=get_auth_headers(token), timeout=15).json()


def api_get_json(token: str, path: str, params: dict = None, timeout: int = 15):
    """GET helper that returns parsed JSON (dict or list) or an error dict."""
    url = f"{API_BASE}{path}" if path.startswith("/") else path
    r = requests.get(url, headers=get_auth_headers(token), params=params, timeout=timeout)
    try:
        return r.json()
    except Exception:
        return {"status": r.status_code, "text": r.text[:2000]}


def attendance(token: str) -> dict:
    """Get student attendance summary + session records (read-only)."""
    url = f"{API_BASE}/api/v1/students/me/attendance/"
    return requests.get(url, headers=get_auth_headers(token), timeout=15).json()


def attendance_day(token: str, tenant_id: str) -> dict:
    """Get day-wise attendance breakdown for the tenant (read-only).

    Returns {total_working_days, present_days, absent_days, ...,
             attendance_percentage, records: [{date, status, reason, class}]}.
    """
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/students/me/attendance/day/"
    return requests.get(url, headers=get_auth_headers(token), timeout=15).json()


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
    """Get notifications (read-only; no mark-read calls).

    Server supports ?limit=&offset=. unread_only is applied client-side
    via is_read so we never mutate state.
    """
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/notifications/?limit={limit}&offset={offset}"
    data = requests.get(url, headers=get_auth_headers(token), timeout=15).json()
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
    return requests.get(url, headers=get_auth_headers(token), params=params, timeout=15).json()


def calendar_events(token: str) -> dict:
    """Get school calendar events."""
    url = f"{API_BASE}/api/v1/school-calendar/events/"
    return requests.get(url, headers=get_auth_headers(token), timeout=15).json()


def assessments(token: str, params: dict = None) -> dict:
    """Get student assessments."""
    url = f"{API_BASE}/api/v1/student/assessments/"
    return requests.get(url, headers=get_auth_headers(token), params=params, timeout=15).json()


def eol_tests(token: str, tenant_id: str, limit: int = None, offset: int = 0) -> dict:
    """Get EOL (end-of-lesson) tests — these are teacher-published assignments.

    Server returns the full list (count ~23); limit/offset are applied
    client-side so output stays stable even if the API ignores the params.
    """
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/eol-tests/my/"
    data = requests.get(url, headers=get_auth_headers(token), timeout=15).json()
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
    return requests.get(url, headers=get_auth_headers(token), timeout=15).json()


def dp_projects(token: str, tenant_id: str):
    """List DP project containers for the tenant (returns [] when none).

    Returns a list (not a dict) — keep as-is so callers can len() it.
    """
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/dp-projects/"
    r = requests.get(url, headers=get_auth_headers(token), timeout=15)
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
    return requests.get(url, headers=get_auth_headers(token), timeout=15).json()


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
    return requests.get(url, headers=get_auth_headers(token), params=params, timeout=15).json()


def get_resource(token: str, tenant_id: str, resource_id: str) -> dict:
    """Get one resource's metadata (folder flag, child_count, file_urls)."""
    url = f"{API_BASE}/api/v1/tenants/{tenant_id}/resources/{resource_id}/"
    return requests.get(url, headers=get_auth_headers(token), timeout=15).json()


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
    r = requests.get(url, headers=get_auth_headers(token), timeout=timeout, stream=True)
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
    return requests.get(url, headers=get_auth_headers(token), timeout=30).json()


def get_topic_content(token: str, unit_id: str) -> dict:
    """Get topic/unit content."""
    url = f"{API_BASE}/api/topic/unit/{unit_id}/"
    return requests.get(url, headers=get_auth_headers(token), timeout=15).json()


def raw_get(token: str, path: str, params: dict = None) -> dict:
    """Raw GET to any API path."""
    url = f"{API_BASE}{path}" if path.startswith("/") else path
    r = requests.get(url, headers=get_auth_headers(token), params=params, timeout=15)
    try:
        return r.json()
    except Exception:
        return {"status": r.status_code, "text": r.text[:2000]}


def pp(data):
    print(json.dumps(data, indent=2, default=str))


def _parse_flags(raw_args):
    """Split CLI args into positionals and --flag values. Supports:
    --json, --unread-only, --inline, --course X, --parent X, --page N,
    --page-size N, --limit N, --offset N, --out DIR."""
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
        elif a in ("--course", "--parent", "--page", "--page-size", "--limit", "--offset", "--out") and i + 1 < len(raw_args):
            flags[a[2:].replace("-", "_")] = raw_args[i + 1]
            i += 1
        else:
            pos.append(a)
        i += 1
    return pos, flags


def main():
    args = sys.argv[1:]

    if not args:
        print("""
IndusLMS Agent CLI (read-only except login)

Core:
  login <email> <password>                Login and save token
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

Environment:
  INDUSLMS_EMAIL    email
  INDUSLMS_PASS     password
  INDUSLMS_TENANT   tenant ID
""")
        return

    cmd = args[0]
    token_data = load_token()
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
        pp(assessments(token))

    elif cmd == "eol-tests":
        if not token:
            print("No token. Run login first.")
            return
        pos, flags = _parse_flags(args[1:])
        tid = pos[0] if pos else (tenant_id or os.environ.get("INDUSLMS_TENANT") or input("Tenant ID: "))
        limit = int(flags["limit"]) if flags.get("limit") else None
        offset = int(flags.get("offset") or 0)
        pp(eol_tests(token, tid, limit=limit, offset=offset))

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

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()