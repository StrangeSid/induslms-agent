#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""School inbox via Apple Mail.app + osascript (JXA). No auth, no network setup.

Reads the account's mailbox directly through Mail.app automation. Zero
credentials, zero app registrations — works because Mail.app already holds
the school session.

Account/mailbox configurable:
  SCHOOL_MAIL_ACCOUNT (default "School"), SCHOOL_MAILBOX (default "Inbox").

CLI:
  python3 mailapp.py folders
  python3 mailapp.py search "assignment" --top 5
  python3 mailapp.py search --sender teacher@indusschool.com --since 2026-09-01
  python3 mailapp.py read <message_id> [--mailbox X]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Optional

ACCOUNT = os.environ.get("SCHOOL_MAIL_ACCOUNT", "School")
DEFAULT_MAILBOX = os.environ.get("SCHOOL_MAILBOX", "Inbox")
TIMEOUT = 120


def _run_js(js: str) -> Any:
    """Run JXA via osascript, return parsed JSON stdout."""
    import shutil
    import sys as _sys

    if _sys.platform != "darwin" or shutil.which("osascript") is None:
        raise RuntimeError(
            "schoolmail_* requires macOS Mail.app + osascript "
            "(unavailable on this platform; use outlook_* instead)"
        )
    r = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", js],
        capture_output=True, text=True, timeout=TIMEOUT,
    )
    if r.returncode != 0:
        raise RuntimeError(f"osascript failed: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout)


def _mailbox_js(mailbox: str) -> str:
    return (
        f'const acc = Application("Mail").accounts["{ACCOUNT}"];'
        f"if (!acc) throw new Error('mail account not found');"
        f'const mbox = acc.mailboxes["{mailbox}"];'
        f"if (!mbox) throw new Error('mailbox not found');"
    )


def list_folders() -> dict[str, Any]:
    js = (
        'const acc = Application("Mail").accounts["%s"];'
        "if (!acc) throw new Error('mail account not found');"
        "JSON.stringify(acc.mailboxes().map(m => "
        "({name: m.name(), count: m.messages.length})))" % ACCOUNT
    )
    rows = _run_js(js)
    return {"account": ACCOUNT, "count": len(rows), "results": rows}


def _normalize(raw: dict[str, Any], mailbox: str) -> dict[str, Any]:
    return {
        "ref": f"{mailbox}:{raw.get('id')}",
        "mailbox": mailbox,
        "id": raw.get("id"),
        "subject": raw.get("subject", "(no subject)"),
        "from": raw.get("sender", "?"),
        "date": raw.get("date", "?"),
        "preview": (raw.get("content") or "")[:200],
        "is_read": raw.get("isRead", True),
    }


def parse_search_output(raw_list: list[dict[str, Any]], mailbox: str) -> list[dict[str, Any]]:
    """Pure: JXA rows -> agent records. Unit-tested, no Mail.app needed."""
    return [_normalize(r, mailbox) for r in raw_list]


def search_inbox(
    query: Optional[str] = None,
    sender: Optional[str] = None,
    since: Optional[str] = None,
    top: int = 10,
    mailbox: str = DEFAULT_MAILBOX,
) -> dict[str, Any]:
    """Search School mailbox (read-only). since = ISO date. Newest first."""
    top = max(1, min(top, 50))
    q = (query or "").replace("\\", "\\\\").replace('"', '\\"')
    s = (sender or "").replace("\\", "\\\\").replace('"', '\\"')
    # JXA whose() takes ONE descriptor: push one predicate server-side,
    # apply the rest in JS below.
    whose = ""
    if query:
        whose = f'.whose({{subject: {{_contains: "{q}"}}}})'
    elif sender:
        whose = f'.whose({{sender: {{_contains: "{s}"}}}})'
    js_filters = ""
    if query and sender:
        js_filters += f'msgs = msgs.filter(m => (m.sender() || "").includes("{s}"));'
    since_js = f'new Date("{since}T00:00:00")' if since else "null"
    js = (
        _mailbox_js(mailbox)
        + f"let msgs = mbox.messages{whose}();"
        + js_filters
        + f"const since = {since_js};"
        + "if (since) msgs = msgs.filter(m => new Date(m.dateReceived()) >= since);"
        + "msgs.sort((a, b) => new Date(b.dateReceived()) - new Date(a.dateReceived()));"
        + f"msgs = msgs.slice(0, {top});"
        + "JSON.stringify(msgs.map(m => ({id: m.id(), subject: m.subject(), "
        + "sender: m.sender(), date: m.dateReceived(), "
        + "content: (m.content() || '').slice(0, 200), isRead: m.readStatus()})))"
    )
    rows = _run_js(js)
    results = parse_search_output(rows, mailbox)
    return {"account": ACCOUNT, "mailbox": mailbox, "count": len(results), "results": results}


def read_message(ref: str, max_body: int = 4000) -> dict[str, Any]:
    """Read one message by ref 'Mailbox:id' (read-only)."""
    mailbox, _, mid = ref.partition(":")
    if not mid:
        mailbox, mid = DEFAULT_MAILBOX, mailbox
    js = (
        _mailbox_js(mailbox)
        + f"const m = mbox.messages.byId({int(mid)});"
        + "JSON.stringify({id: m.id(), subject: m.subject(), sender: m.sender(), "
        + "recipients: m.recipients().map(r => r.address()), "
        + "date: m.dateReceived(), content: m.content() || '', "
        + "isRead: m.readStatus(), attachments: m.mailAttachments().map(a => a.name())})"
    )
    data = _run_js(js)
    body = data.get("content") or ""
    if len(body) > max_body:
        body = body[:max_body] + f"\n…[truncated {len(body) - max_body} chars]"
    data["content"] = body
    data["ref"] = ref
    data["from"] = data.get("sender", "?")
    return data


def summarize_messages(data: dict[str, Any], limit_rows: int = 15) -> str:
    msgs = (data.get("results") or [])[:limit_rows]
    lines = [f"messages: {data.get('count', len(msgs))} (showing {len(msgs)})"]
    for m in msgs:
        state = "read" if m.get("is_read", True) else "UNREAD"
        lines.append(f"  [{state}] {(m.get('date') or '?')[:10]} from={m.get('from', '?')}")
        lines.append(f"    {m.get('subject', '(no subject)')}")
        if m.get("preview"):
            lines.append(f"    {m['preview'][:120]}")
    return "\n".join(lines)


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, rest = args[0], args[1:]
    if cmd == "folders":
        print(json.dumps(list_folders(), indent=2, default=str))
    elif cmd == "search":
        query, sender, since, top, mailbox, as_json = None, None, None, 10, DEFAULT_MAILBOX, False
        i = 0
        while i < len(rest):
            if rest[i] == "--sender" and i + 1 < len(rest):
                sender = rest[i + 1]; i += 2
            elif rest[i] == "--since" and i + 1 < len(rest):
                since = rest[i + 1]; i += 2
            elif rest[i] == "--top" and i + 1 < len(rest):
                top = int(rest[i + 1]); i += 2
            elif rest[i] == "--mailbox" and i + 1 < len(rest):
                mailbox = rest[i + 1]; i += 2
            elif rest[i] == "--json":
                as_json = True; i += 1
            else:
                query = (query + " " + rest[i]).strip() if query else rest[i]; i += 1
        data = search_inbox(query, sender, since, top, mailbox)
        print(json.dumps(data, indent=2, default=str) if as_json else summarize_messages(data))
    elif cmd == "read":
        if not rest:
            print("Usage: mailapp.py read <Mailbox:id> [--max-body N]"); sys.exit(2)
        max_body = int(rest[rest.index("--max-body") + 1]) if "--max-body" in rest else 4000
        data = read_message(rest[0], max_body)
        print(f"Subject: {data.get('subject')}\nFrom: {data.get('from')}\nDate: {data.get('date')}\n")
        print(data.get("content", ""))
    else:
        print(f"Unknown command: {cmd}\n{__doc__}")
        sys.exit(1)


if __name__ == "__main__":
    main()
