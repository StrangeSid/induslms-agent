"""Parent-role calls: exact paths, child scoping and MCP registry (no network)."""

import asyncio
import json

import pytest

import lms


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.ok = status < 400
        self._body = body
        self.content = b"" if body is None else json.dumps(body).encode()
        self.text = self.content.decode()

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class FakeHTTP:
    def __init__(self, *answers):
        self.calls = []
        self.answers = list(answers)

    def request(self, method, url, **kw):
        self.calls.append({"method": method, "url": url, **kw})
        return self.answers.pop(0) if self.answers else FakeResponse(200, {})

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)


@pytest.fixture
def http(monkeypatch):
    fake = FakeHTTP()
    monkeypatch.setattr(lms, "HTTP", fake)
    return fake


def path(call):
    return call["url"].replace(lms.API_BASE, "")


def test_parent_children_and_child_courses(http):
    http.answers.append(FakeResponse(200, {"count": 1, "results": [
        {"student_profile_id": "sp1", "user_id": "u1", "full_name": "Child One"}]}))
    rows = lms.parent_children("tok")
    assert path(http.calls[0]) == "/api/v1/parents/me/children"
    assert rows[0]["student_profile_id"] == "sp1"

    lms.parent_child_courses("tok", "tid", "sp1", year="2026-27")
    call = http.calls[1]
    assert path(call) == "/api/v1/tenants/tid/parents/me/children/sp1/courses/"
    assert call["params"] == {"year": "2026-27", "include_teachers": "true",
                              "include_classes": "true"}


def test_parent_calendar_uses_from_to_and_attendance_summary(http):
    lms.parent_child_calendar("tok", "tid", "sp1", "2026-11-01", "2026-11-30")
    call = http.calls[0]
    assert path(call) == "/api/v1/tenants/tid/parents/me/children/sp1/calendar/"
    assert call["params"] == {"from": "2026-11-01", "to": "2026-11-30"}

    http.answers.append(FakeResponse(200, [{"student_id": "sp1"}]))
    rows = lms.parent_attendance("tok", "2026-10-01", "2026-10-31")
    assert path(http.calls[1]) == "/api/v1/parents/me/attendance/"
    assert http.calls[1]["params"] == {"from_date": "2026-10-01", "to_date": "2026-10-31"}
    assert rows == [{"student_id": "sp1"}]


def test_parent_child_learner_profile(http):
    lms.parent_child_learner_profile("tok", "sp1", "2026-27")
    call = http.calls[0]
    assert path(call) == "/api/v1/parents/children/sp1/learner-profile"
    assert call["params"] == {"year": "2026-27"}


def test_student_id_is_forwarded_on_child_scoped_reads(http):
    lms.assessments_all("tok", "FA", student_id="sp1")
    assert http.calls[0]["params"]["student_id"] == "sp1"
    assert path(http.calls[0]) == "/api/v1/student/assessments/"

    lms.assessment_submission("tok", "a1", student_id="sp1")
    assert path(http.calls[1]) == "/api/v1/student/assessments/a1/submission/"
    assert http.calls[1]["params"] == {"student_id": "sp1"}

    lms.assessment_feedback("tok", "a1", student_id="sp1")
    assert path(http.calls[2]) == "/api/v1/student/assessments/a1/feedback/"

    lms.eol_tests("tok", "tid", course_id="c1", year="2026-27", student_id="sp1")
    assert path(http.calls[3]) == "/api/v1/tenants/tid/eol-tests/my/"
    assert http.calls[3]["params"] == {"course_id": "c1", "year": "2026-27",
                                       "student_id": "sp1"}

    lms.learning_tasks("tok", "tid", "c1", student_id="sp1")
    assert http.calls[4]["params"] == {"course_id": "c1", "student_id": "sp1"}

    lms.learning_task_detail("tok", "tid", "t1", student_id="sp1")
    assert http.calls[5]["params"] == {"student_id": "sp1"}

    lms.list_resources("tok", "tid", "c1", student_id="sp1")
    assert http.calls[6]["params"]["student_id"] == "sp1"

    lms.get_resource("tok", "tid", "r1", student_id="sp1")
    assert http.calls[7]["params"] == {"student_id": "sp1"}

    lms.notifications("tok", "tid", 5, 0, student_id="sp1")
    assert path(http.calls[8]) == "/api/v1/tenants/tid/notifications/"
    assert http.calls[8]["params"] == {"limit": 5, "offset": 0, "student_id": "sp1"}

    lms.announcements_visible("tok", "2026-27", student_id="sp1")
    assert path(http.calls[9]) == "/api/announcements/visible/"
    assert http.calls[9]["params"] == {"academic_year": "2026-27", "student_id": "sp1"}

    lms.message_contacts("tok", "tid", student_id="sp1")
    assert path(http.calls[10]) == "/api/v1/tenants/tid/messages/contacts/"
    assert http.calls[10]["params"] == {"student_id": "sp1"}

    lms.attendance_day("tok", "tid", student_id="sp1", from_date="2026-09-01",
                       to_date="2026-09-30")
    assert path(http.calls[11]) == "/api/v1/tenants/tid/students/me/attendance/day/"
    assert http.calls[11]["params"] == {"student_id": "sp1",
                                        "from_date": "2026-09-01", "to_date": "2026-09-30"}


def test_student_reads_unchanged_without_student_id(http):
    lms.assessments_all("tok", "SA")
    assert http.calls[0]["params"] == {"page": 1, "page_size": 100, "assessment_type": "SA"}
    lms.eol_tests("tok", "tid")
    assert http.calls[1]["params"] is None
    lms.learning_tasks("tok", "tid")
    assert http.calls[2]["params"] is None
    lms.message_contacts("tok", "tid")
    assert http.calls[3]["params"] is None


def test_parent_overview_scopes_each_child(http, monkeypatch):
    seen = {}

    monkeypatch.setattr(lms, "parent_children", lambda t: [
        {"student_profile_id": "sp1", "full_name": "One", "academic_year": "2026-27"},
        {"student_profile_id": "sp2", "full_name": "Two", "academic_year": "2026-27"},
    ])
    monkeypatch.setattr(lms, "parent_child_courses",
                        lambda t, tid, sid, year=None: seen.setdefault("courses", []).append(sid) or {})
    monkeypatch.setattr(lms, "eol_tests",
                        lambda t, tid, **kw: seen.setdefault("eol", []).append(kw.get("student_id")) or {})
    monkeypatch.setattr(lms, "assessments_all",
                        lambda t, kind, **kw: seen.setdefault("assess", []).append((kind, kw.get("student_id"))) or [])
    monkeypatch.setattr(lms, "learning_tasks",
                        lambda t, tid, **kw: seen.setdefault("tasks", []).append(kw.get("student_id")) or [])
    monkeypatch.setattr(lms, "list_resources",
                        lambda t, tid, **kw: seen.setdefault("resources", []).append(kw.get("student_id")) or {})

    out = lms.parent_overview("tok", "tid", "sp1")
    assert [c["child"]["student_profile_id"] for c in out["children"]] == ["sp1"]
    assert seen["courses"] == ["sp1"]
    assert seen["eol"] == ["sp1"]
    assert seen["tasks"] == ["sp1"]
    assert seen["resources"] == ["sp1"]
    assert seen["assess"][0] == ("FA", "sp1") and seen["assess"][1] == ("SA", "sp1")


def test_parents_mcp_registry():
    import server

    async def tools():
        return {t.name: t for t in await server.mcp.list_tools()}

    registry = asyncio.run(tools())
    for name in ("list_children", "child_courses", "child_attendance", "child_calendar",
                 "child_learner_profile", "child_overview"):
        assert name in registry, f"missing parent tool: {name}"
    # Scoped reads accept the child id without a separate tool per role.
    import inspect

    for name in ("list_assessments", "list_eol", "list_learning_tasks", "list_resources",
                 "get_assessment_submission", "get_assessment_feedback", "list_notifications",
                 "get_attendance_day"):
        sig = inspect.signature(getattr(server, name))
        assert "student_profile_id" in sig.parameters, f"{name} missing student_profile_id"
    # Writes that submit work must not exist as parent tools.
    assert not any(n.startswith("parent_submit") for n in registry)
