"""Write and detail calls: exact paths/payloads and error mapping (no network)."""

import base64
import json
import time

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
    """Records every request; answers from a queue (default 200 {})."""

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


def test_eol_open_uses_short_id_and_submit_uses_uuid(http):
    lms.eol_open("tok", "tid", " ECO082 ", "1234 ")
    assert path(http.calls[0]) == "/api/v1/tenants/tid/eol-tests/open/"
    assert http.calls[0]["json"] == {"test_id": "ECO082", "passcode": "1234"}
    assert http.calls[0]["headers"]["Authorization"] == "Bearer tok"

    lms.eol_submit("tok", "tid", "uuid-1", "1234", {"q1": "B", "q2": "a"})
    call = http.calls[1]
    assert path(call) == "/api/v1/tenants/tid/eol-tests/uuid-1/submit/"
    assert call["json"] == {"test_id": "uuid-1", "passcode": "1234", "answers": [
        {"question_id": "q1", "selected_option": "b"}, {"question_id": "q2", "selected_option": "a"}]}


def test_eol_submit_rejects_unanswered_or_bad_options(http):
    with pytest.raises(ValueError):
        lms.eol_submit("tok", "tid", "uuid-1", "1234", {"q1": ""})
    with pytest.raises(ValueError):
        lms.eol_submit("tok", "tid", "uuid-1", "1234", [{"question_id": "q1", "selected_option": "e"}])
    assert http.calls == []


def test_errors_raise_with_message_and_code(http):
    http.answers.append(FakeResponse(403, {"code": "attempts_exceeded", "message": "All attempts used.",
                                           "status": 403, "request_id": "r"}))
    with pytest.raises(lms.LMSError) as e:
        lms.eol_open("tok", "tid", "ECO082", "1")
    assert e.value.status == 403
    assert e.value.code == "attempts_exceeded"
    assert str(e.value) == "All attempts used."


def test_error_message_shapes():
    assert lms.error_message({"detail": "Nope"}) == "Nope"
    assert lms.error_message({"reason": ["Too short."]}) == "reason: Too short."
    assert lms.error_message({"non_field_errors": ["Past due."]}) == "Past due."
    assert lms.error_message("plain") == "plain"


def test_task_upload_and_submit(http):
    http.answers += [FakeResponse(200, {"upload_url": "https://s3.example/put?sig=1", "file_url": "https://s3.example/f.pdf"}),
                     FakeResponse(200, None), FakeResponse(201, {"ok": True})]
    files = lms.upload_files("tok", "tid", lms.TASK_UPLOAD_MODULE, [("work.pdf", b"%PDF", None)])
    slot, put = http.calls[0], http.calls[1]
    assert path(slot) == "/api/v1/s3uploads/get-upload-url/"
    assert slot["json"]["module"] == "assignment_submission"
    assert slot["json"]["content_type"] == "application/pdf"
    assert put["method"] == "PUT" and put["url"].startswith("https://s3.example/put")
    assert "Authorization" not in put["headers"]  # presigned URL, never the LMS token
    assert files == [{"file_url": "https://s3.example/f.pdf", "name": "work.pdf",
                      "content_type": "application/pdf", "size_bytes": 4}]

    lms.task_submit("tok", "tid", "task-1", files)
    assert path(http.calls[2]) == "/api/v1/tenants/tid/assignments/student/task-1/submit/"
    assert http.calls[2]["json"] == {"submission_text": "", "submission_files": files}


def test_assessment_module_keeps_the_typo():
    assert lms.ASSESSMENT_UPLOAD_MODULE == "assesement"


def test_task_submit_needs_a_file(http):
    with pytest.raises(ValueError):
        lms.task_submit("tok", "tid", "task-1", [])


def test_fa_writes(http):
    lms.assessment_submit_upload("tok", "a1", ["https://s3/x.pdf"], "done")
    assert path(http.calls[0]) == "/api/v1/student/assessments/a1/submit-upload/"
    assert http.calls[0]["json"] == {"submission_urls": ["https://s3/x.pdf"], "comment": "done", "assessment_id": "a1"}
    lms.assessment_submit_questions("tok", "a1", [{"question_id": "q", "answer_text": "42"}])
    assert path(http.calls[1]) == "/api/v1/student/assessments/a1/submit-questions/"
    lms.assessment_resubmit("tok", "a1", [0], ["https://s3/y.pdf"], comment="v2", base_submitted_at="2026-10-01T00:00:00Z")
    assert http.calls[2]["json"] == {"keep_indexes": [0], "new_files": ["https://s3/y.pdf"],
                                     "base_submitted_at": "2026-10-01T00:00:00Z", "comment": "v2"}
    lms.assessment_request("tok", "a1", "extension", " Need two more days, was ill ", "2026-10-20T10:00:00Z")
    assert path(http.calls[3]) == "/api/v1/student/assessments/a1/requests/"
    assert http.calls[3]["json"] == {"request_type": "extension", "reason": "Need two more days, was ill",
                                     "preferred_due_at": "2026-10-20T10:00:00Z"}
    lms.request_cancel("tok", "r1")
    assert path(http.calls[4]) == "/api/v1/student/requests/r1/cancel/"
    with pytest.raises(ValueError):
        lms.assessment_request("tok", "a1", "regrade", "please please")


def test_messaging_and_mark_read(http):
    http.answers.append(FakeResponse(200, {"count": 2, "results": [{"id": "new"}, {"id": "old"}]}))
    convo = lms.message_conversation("tok", "tid", "u2")
    assert [m["id"] for m in convo["results"]] == ["old", "new"]
    lms.send_message("tok", "tid", "u2", "  Hello  ")
    assert path(http.calls[1]) == "/api/v1/tenants/tid/messages/"
    assert http.calls[1]["json"] == {"to_user_id": "u2", "text": "Hello"}
    with pytest.raises(ValueError):
        lms.send_message("tok", "tid", "u2", "   ")
    lms.notification_read("tok", "tid", "n1")
    lms.notifications_read_all("tok", "tid")
    lms.announcement_read("tok", "a9")
    assert [path(c) for c in http.calls[2:]] == ["/api/v1/tenants/tid/notifications/n1/read/",
                                                  "/api/v1/tenants/tid/notifications/read-all/",
                                                  "/api/announcements/a9/read/"]


def test_reads_paths_and_pagination(http):
    http.answers += [FakeResponse(200, {"count": 3, "next": "p2", "results": [{"id": 1}, {"id": 2}]}),
                     FakeResponse(200, {"count": 3, "next": None, "results": [{"id": 3}]})]
    rows = lms.assessments_all("tok", "FA")
    assert [r["id"] for r in rows] == [1, 2, 3]
    assert http.calls[1]["params"] == {"page": 2, "page_size": 100, "assessment_type": "FA"}

    http.answers += [FakeResponse(200, {"enabled": True, "items": {"a": {}}}), FakeResponse(200, {"enabled": True, "items": {"b": {}}})]
    out = lms.request_summary("tok", [f"id{i}" for i in range(60)])
    assert set(out["items"]) == {"a", "b"}
    assert len(http.calls[3]["params"]["assessment_ids"].split(",")) == 10

    lms.eol_result("tok", "tid", "uuid-1", "u1")
    assert path(http.calls[4]) == "/api/v1/tenants/tid/eol-tests/uuid-1/students/u1/"


def test_policies_dedupe_across_years(http):
    http.answers += [FakeResponse(200, [{"program_year_id": "y1"}, {"program_year_id": "y2"}]),
                     FakeResponse(200, [{"title": "Uniform Policy"}, {"title": "Exam Policy"}]),
                     FakeResponse(200, [{"title": "uniform policy "}, {"title": "Library Policy"}])]
    assert [p["title"] for p in lms.policies("tok", "tid")] == ["Uniform Policy", "Exam Policy", "Library Policy"]
    assert path(http.calls[1]) == "/api/v1/tenants/tid/academic-years/y1/policies/"


def _jwt(exp):
    part = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{part({'alg': 'none'})}.{part({'exp': exp})}.sig"


def test_ensure_fresh_token_refreshes_and_saves(tmp_path, monkeypatch, http):
    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps({"access": _jwt(time.time() - 10), "refresh": "r1", "user": {"id": "u"}}))
    monkeypatch.setattr(lms, "TOKEN_FILE", str(token_file))
    fresh = _jwt(time.time() + 3600)
    http.answers.append(FakeResponse(200, {"access": fresh, "refresh": "r2"}))
    data = lms.ensure_fresh_token()
    assert data["access"] == fresh and data["refresh"] == "r2"
    assert json.loads(token_file.read_text())["refresh"] == "r2"
    assert (token_file.stat().st_mode & 0o777) == 0o600
    # Still fresh: no second refresh call.
    lms.ensure_fresh_token()
    assert len(http.calls) == 1


def test_mcp_never_uploads_hidden_files_or_the_token(tmp_path, monkeypatch):
    import server

    secret = tmp_path / ".ssh" / "id_rsa"
    secret.parent.mkdir()
    secret.write_text("x")
    token_file = tmp_path / "token.json"
    token_file.write_text("{}")
    monkeypatch.setattr(lms, "TOKEN_FILE", str(token_file))
    for bad in (secret, token_file):
        with pytest.raises(ValueError):
            server._local_files([str(bad)])
    ok = tmp_path / "essay.pdf"
    ok.write_bytes(b"%PDF")
    assert server._local_files([str(ok)]) == [("essay.pdf", b"%PDF", None)]


def test_mcp_write_tools_registered_but_no_test_taking():
    import asyncio
    import server

    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    for expected in ("send_message", "mark_notification_read", "mark_all_notifications_read",
                     "mark_announcement_read", "request_extension_or_resubmission", "cancel_request",
                     "submit_assessment_files", "submit_learning_task", "get_eol_result",
                     "list_learning_tasks", "get_conversation", "list_policies"):
        assert expected in names, expected
    assert not {"eol_open", "eol_submit", "submit_eol", "take_test"} & names
    writes = [t for t in tools if (t.description or "").startswith("WRITE")]
    assert len(writes) >= 8
