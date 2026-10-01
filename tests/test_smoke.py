"""Smoke tests: imports + read-only helpers (no network, no token)."""

import importlib


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
                     "get_attendance", "list_announcements"):
        assert expected in tools, f"missing MCP tool: {expected}"
