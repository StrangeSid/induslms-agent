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
        "resources": {"count": 0, "results": []},
    }
    text = lms.summarize_assignments(overview)
    assert "EOL tests: 1" in text

    notifs = {"unread_count": 1, "results": [{
        "type": "eol", "title": "N", "message": "m",
        "link": "/assignments/test/x/eol", "course_id": "c",
        "is_read": False}]}
    assert "UNREAD" in lms.summarize_notifications(notifs)


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
                     "od_resolve_link", "od_browse", "od_download"):
        assert expected in tools, f"missing MCP tool: {expected}"


def test_outlook_helpers_no_network():
    import outlook

    # cache outside repo
    assert outlook.TOKEN_CACHE.startswith(os.path.expanduser("~"))
    assert "induslms-agent" not in outlook.TOKEN_CACHE
    # least privilege
    assert outlook.SCOPES == ["Mail.Read"]

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
