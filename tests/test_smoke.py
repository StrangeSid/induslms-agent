"""Smoke tests: imports + read-only helpers (no network, no token)."""

import importlib
import os


def test_imports():
    import lms
    import server

    assert hasattr(lms, "assignments_overview")
    assert hasattr(lms, "download_resource_file")
    assert hasattr(lms, "summarize_assignments")
    assert hasattr(server, "mcp")


def test_summarizers():
    import lms

    overview = {
        "eol": {"count": 1, "results": [{
            "status": "assigned", "title": "T", "subject": "S",
            "topic": "T", "score": None, "total_marks": "5.00",
            "expires_message": "soon"}]},
        "assessments": {"count": 0, "results": []},
        "tasks": [{"status": "assigned", "title": "HW1", "subject": "Math", "due_date": "2026-10-15"}],
        "resources": {"count": 0, "results": []},
    }
    text = lms.summarize_assignments(overview)
    assert "EOL tests: 1" in text
    assert "Learning tasks: 1 total" in text
    assert "HW1" in text

    notifs = {"unread_count": 1, "results": [{
        "type": "eol", "title": "N", "message": "m",
        "link": "/assignments/test/x/eol", "course_id": "c",
        "is_read": False}]}
    assert "UNREAD" in lms.summarize_notifications(notifs)


def test_assignments_overview_includes_tasks(monkeypatch):
    import lms

    monkeypatch.setattr(lms, "eol_tests", lambda tok, tid: {"count": 0, "results": []})
    monkeypatch.setattr(lms, "assessments", lambda tok: {"count": 0, "results": []})
    monkeypatch.setattr(lms, "learning_tasks", lambda tok, tid, course_id=None: [{"id": "t1", "course_id": course_id}])
    monkeypatch.setattr(lms, "list_resources", lambda tok, tid, course_id=None, page_size=20: {"count": 0, "results": []})

    out = lms.assignments_overview("tok", "tid", course_id="c123")
    assert out["course_id"] == "c123"
    assert "tasks" in out
    assert out["tasks"] == [{"id": "t1", "course_id": "c123"}]


def test_session_context_tenant_extraction(monkeypatch):
    import lms

    # 1. roles inside user
    tok1 = {"access": "acc1", "user": {"id": "u1", "roles": [{"tenant_id": "tid-user"}]}}
    monkeypatch.setattr(lms, "ensure_fresh_token", lambda margin=300: tok1)
    acc, tid, uid = lms.session_context()
    assert acc == "acc1" and tid == "tid-user" and uid == "u1"

    # 2. top-level roles
    tok2 = {"access": "acc2", "roles": [{"tenant_id": "tid-roles"}]}
    monkeypatch.setattr(lms, "ensure_fresh_token", lambda margin=300: tok2)
    acc, tid, uid = lms.session_context()
    assert acc == "acc2" and tid == "tid-roles"

    # 3. top-level tenant_id
    tok3 = {"access": "acc3", "tenant_id": "tid-top"}
    monkeypatch.setattr(lms, "ensure_fresh_token", lambda margin=300: tok3)
    acc, tid, uid = lms.session_context()
    assert acc == "acc3" and tid == "tid-top"

    # 4. env fallback
    tok4 = {"access": "acc4"}
    monkeypatch.setattr(lms, "ensure_fresh_token", lambda margin=300: tok4)
    monkeypatch.setenv("INDUSLMS_TENANT", "tid-env")
    acc, tid, uid = lms.session_context()
    assert acc == "acc4" and tid == "tid-env"


def test_mcp_tools_registered():
    import asyncio
    import server

    async def names():
        return sorted(t.name for t in await server.mcp.list_tools())

    tools = asyncio.run(names())
    for expected in ("assignments_overview", "list_resources",
                     "download_resource", "list_notifications",
                     "get_attendance", "list_announcements",
                     "outlook_search", "outlook_read", "outlook_folders",
                     "schoolmail_search", "schoolmail_read", "schoolmail_folders",
                     "od_resolve_link", "od_browse", "od_list_sites", "od_download"):
        assert expected in tools, f"missing MCP tool: {expected}"


def test_outlook_helpers_no_network(monkeypatch):
    import outlook

    # cache outside repo
    assert outlook.TOKEN_CACHE.startswith(os.path.expanduser("~"))
    assert "induslms-agent" not in outlook.TOKEN_CACHE
    # least privilege
    assert outlook.SCOPES == ["Mail.Read"]
    # no-registration chain: Office first, Thunderbird fallback
    monkeypatch.delenv(outlook.CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(outlook.BUILTIN_OPT_IN_ENV, raising=False)
    assert outlook.client_candidates() == [
        outlook.BUILTIN_CLIENT_ID, outlook.THUNDERBIRD_CLIENT_ID]
    assert outlook.THUNDERBIRD_CLIENT_ID == "08162f7c-0fd2-4200-a84a-f25a4db0b584"
    assert set(outlook.ALL_SCOPES) >= set(outlook.SCOPES)
    # explicit id wins
    monkeypatch.setenv(outlook.CLIENT_ID_ENV, "custom-id")
    assert outlook.client_candidates() == ["custom-id"]
    # opt-out forces explicit
    monkeypatch.delenv(outlook.CLIENT_ID_ENV, raising=False)
    monkeypatch.setenv(outlook.BUILTIN_OPT_IN_ENV, "0")
    try:
        outlook.client_candidates()
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass

    path, params = outlook.build_search_params("homework", "t@indusschool.com", "2026-09-01", 5)
    assert path == "/me/mailFolders/inbox/messages"
    assert params["$search"] == '"homework" from:t@indusschool.com'
    assert params["$filter"] == "receivedDateTime ge 2026-09-01"
    assert params["$top"] == 5

    text = outlook.summarize_messages({"count": 0, "results": []})
    assert "messages: 0" in text


def test_sharepoint_helpers_no_network():
    import sharepoint

    # least privilege, read-only
    assert sharepoint.SCOPES == ["Files.Read", "Sites.Read.All"]

    # encoder: determinism + round-trip + known shape (u! + base64url, no padding)
    t1 = sharepoint.encode_sharing_url("https://example.com/a?b=c&d=e/f+g")
    t2 = sharepoint.encode_sharing_url("https://example.com/a?b=c&d=e/f+g")
    assert t1 == t2 and t1.startswith("u!") and "=" not in t1
    assert "/" not in t1[2:] and "+" not in t1[2:]
    import base64

    padded = t1[2:].replace("-", "+").replace("_", "/")
    padded += "=" * (-len(padded) % 4)
    assert base64.b64decode(padded).decode() == "https://example.com/a?b=c&d=e/f+g"

    assert sharepoint.build_browse_path() == "/me/drive/root/children"
    assert sharepoint.build_browse_path("Math/Notes") == "/me/drive/root:/Math/Notes:/children"
    assert sharepoint.build_browse_path("/", site_id="SID") == "/sites/SID/drive/root/children"

    text = sharepoint.summarize_items({"count": 1, "results": [
        {"name": "HW.pdf", "id": "1"}]})
    assert "[FILE] HW.pdf" in text


def test_graph_mcp_gate_accepts_builtin(monkeypatch):
    import outlook
    import server

    monkeypatch.delenv(outlook.CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(outlook.BUILTIN_OPT_IN_ENV, raising=False)
    # no env: builtin chain still configures MCP tools (no Azure app needed)
    assert server._outlook() is outlook
    monkeypatch.setenv(outlook.BUILTIN_OPT_IN_ENV, "0")
    try:
        server._outlook()
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


def test_browser_login_no_typing(monkeypatch):
    import outlook

    monkeypatch.delenv(outlook.CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(outlook.BUILTIN_OPT_IN_ENV, raising=False)
    calls: list[str] = []

    class FakeApp:
        def __init__(self, cid):
            self.cid = cid
            self.token_cache = object()

        def acquire_token_interactive(self, scopes, prompt=None, timeout=None):
            calls.append((self.cid, tuple(scopes)))
            if self.cid == outlook.BUILTIN_CLIENT_ID:
                return {"error": "unauthorized_client",
                        "error_description": "unauthorized_client: unknown client"}
            return {"access_token": "x", "token_type": "Bearer"}

        def get_accounts(self):
            return [{"username": "s@indusschool.com"}]

    monkeypatch.setattr(outlook, "build_app", FakeApp)
    monkeypatch.setattr(outlook, "_save_cache", lambda c: None)
    out = outlook.browser_login()
    assert out["account"] == "s@indusschool.com"
    # Office tried (all tiers fail fast on first? no — unauthorized retries
    # next client), Thunderbird succeeds on full tier first
    assert calls[0][0] == outlook.BUILTIN_CLIENT_ID
    assert calls[-1][0] == outlook.THUNDERBIRD_CLIENT_ID
    assert calls[-1][1] == tuple(outlook.ALL_SCOPES)


def test_browser_login_retries_65002_with_reduced_scopes(monkeypatch):
    import outlook

    monkeypatch.delenv(outlook.CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(outlook.BUILTIN_OPT_IN_ENV, raising=False)
    seen: list[tuple[str, tuple]] = []

    class FakeApp:
        def __init__(self, cid):
            self.cid = cid
            self.token_cache = object()

        def acquire_token_interactive(self, scopes, prompt=None, timeout=None):
            seen.append((self.cid, tuple(scopes)))
            if "Sites.Read.All" in scopes:
                return {"error": "invalid_grant",
                        "error_description": "AADSTS65002: preauthorization required"}
            return {"access_token": "x", "token_type": "Bearer"}

        def get_accounts(self):
            return [{"username": "s@indusschool.com"}]

    monkeypatch.setattr(outlook, "build_app", FakeApp)
    monkeypatch.setattr(outlook, "_save_cache", lambda c: None)
    monkeypatch.setattr(outlook, "client_candidates", lambda: ["cid-1"])
    out = outlook.browser_login()
    assert out["account"] == "s@indusschool.com"
    assert seen[0][1] == tuple(outlook.ALL_SCOPES)
    assert "Sites.Read.All" not in seen[-1][1]


def test_mailapp_parse_noosascript():
    import mailapp

    rows = [{"id": 7, "subject": "HW", "sender": "T <t@indusschool.com>",
             "date": "2026-09-01T00:00:00Z", "content": "do x" * 100, "isRead": False}]
    recs = mailapp.parse_search_output(rows, "Inbox")
    assert recs[0]["ref"] == "Inbox:7"
    assert recs[0]["from"] == "T <t@indusschool.com>"
    assert recs[0]["is_read"] is False
    assert len(recs[0]["preview"]) == 200
    assert "UNREAD" in mailapp.summarize_messages({"count": 1, "results": recs})
