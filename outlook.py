#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""School Outlook inbox access via Microsoft Graph (read-only).

Auth: MSAL device-code flow, delegated ``Mail.Read`` only.
Token cache lives OUTSIDE the repo (never committed; see .gitignore).

Setup (one time):
  1. Azure Portal -> Microsoft Entra ID -> App registrations -> New:
     - Supported account types: multitenant (or single-tenant in your
       school tenant if IT prefers). Enable "Allow public client flows".
     - API permissions -> add delegated ``Mail.Read``.
   2. export INDUS_OUTLOOK_CLIENT_ID=<app (client) id>
      [optional] export INDUS_OUTLOOK_AUTHORITY=https://login.microsoftonline.com/organizations
      (no registration? export INDUS_USE_BUILTIN_CLIENT=1 instead — uses
      the pre-consented Microsoft Office client; you sign in as yourself)
   3. python3 outlook.py login   # prints a code; approve in the browser
  4. python3 outlook.py search "assignment" --top 5

If the school tenant blocks user consent, an IT admin must grant admin
consent for Mail.Read on the app registration first.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

import msal
import requests

try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv()
except Exception:
    pass

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["Mail.Read"]

CLIENT_ID_ENV = "INDUS_OUTLOOK_CLIENT_ID"
AUTHORITY_ENV = "INDUS_OUTLOOK_AUTHORITY"
TOKEN_CACHE_ENV = "INDUS_OUTLOOK_TOKEN_FILE"
BUILTIN_OPT_IN_ENV = "INDUS_USE_BUILTIN_CLIENT"
# Microsoft Office (first-party, pre-consented). Used ONLY when explicitly
# opted in via INDUS_USE_BUILTIN_CLIENT=1 — no app registration needed.
BUILTIN_CLIENT_ID = "d3590ed6-52b3-4102-aeff-aad2292ab01c"
DEFAULT_AUTHORITY = "https://login.microsoftonline.com/common"
TOKEN_CACHE = os.path.expanduser(os.environ.get(TOKEN_CACHE_ENV, "~/.indus_outlook_token.json"))


def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE):
        with open(TOKEN_CACHE) as f:
            cache.deserialize(f.read())
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    with open(TOKEN_CACHE, "w") as f:
        f.write(cache.serialize())


def _client_id() -> str:
    cid = os.environ.get(CLIENT_ID_ENV)
    if cid:
        return cid
    if os.environ.get(BUILTIN_OPT_IN_ENV) == "1":
        return BUILTIN_CLIENT_ID
    raise RuntimeError(
        f"Set {CLIENT_ID_ENV} to your Entra app (client) id, or set "
        f"{BUILTIN_OPT_IN_ENV}=1 to use the pre-consented Microsoft Office "
        "client (no registration; you sign in as yourself)."
    )


def build_app() -> msal.PublicClientApplication:
    cache = _load_cache()
    return msal.PublicClientApplication(
        _client_id(),
        authority=os.environ.get(AUTHORITY_ENV, DEFAULT_AUTHORITY),
        token_cache=cache,
    )


def device_login() -> dict[str, Any]:
    """Interactive device-code login. Prints the code, blocks until approved."""
    app = build_app()
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow failed: {flow.get('error_description', flow)}")
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    _save_cache(app.token_cache)
    if "access_token" not in result:
        raise RuntimeError(f"Login failed: {result.get('error_description', result)}")
    account = (app.get_accounts() or [{}])[0]
    print(f"[+] Outlook login ok for {account.get('username', 'unknown')}")
    return {"account": account.get("username"), "token_type": result.get("token_type")}


def get_token() -> str:
    """Silent token from cache (refreshes automatically). Raises with login hint."""
    app = build_app()
    accounts = app.get_accounts()
    if not accounts:
        raise RuntimeError("No Outlook login. Run `python3 outlook.py login` first.")
    result = app.acquire_token_silent(SCOPES, accounts[0])
    if not result or "access_token" not in result:
        raise RuntimeError(
            "Cached Outlook token expired and silent refresh failed. "
            "Run `python3 outlook.py login` again."
        )
    _save_cache(app.token_cache)
    return result["access_token"]


def graph_get(token: str, path: str, params: Optional[dict] = None) -> Any:
    url = f"{GRAPH_BASE}{path}"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params=params,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def build_search_params(
    query: Optional[str] = None,
    sender: Optional[str] = None,
    since: Optional[str] = None,
    top: int = 10,
    folder: str = "inbox",
) -> tuple[str, dict]:
    """Pure helper: Graph path + $search/$filter/$select params for a mail query."""
    path = "/me/mailFolders/inbox/messages" if folder == "inbox" else "/me/messages"
    terms = []
    if query:
        terms.append(f'"{query}"')
    if sender:
        terms.append(f"from:{sender}")
    params: dict[str, Any] = {
        "$top": max(1, min(top, 50)),
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,hasAttachments",
    }
    if terms:
        params["$search"] = " ".join(terms)
    if since:
        params["$filter"] = f"receivedDateTime ge {since}"
    return path, params


def search_inbox(
    query: Optional[str] = None,
    sender: Optional[str] = None,
    since: Optional[str] = None,
    top: int = 10,
) -> dict[str, Any]:
    """Search the inbox (read-only). since = ISO date, e.g. 2026-09-01."""
    token = get_token()
    path, params = build_search_params(query, sender, since, top)
    data = graph_get(token, path, params)
    return {"count": len(data.get("value", [])), "results": data.get("value", [])}


def read_message(message_id: str, max_body: int = 4000) -> dict[str, Any]:
    """Read one message (subject, from, date, preview + truncated body)."""
    token = get_token()
    data = graph_get(
        token,
        f"/me/messages/{message_id}",
        {"$select": "id,subject,from,toRecipients,receivedDateTime,bodyPreview,body,hasAttachments"},
    )
    body = ((data.get("body") or {}).get("content") or "")
    if len(body) > max_body:
        body = body[:max_body] + f"\n…[truncated {len(body) - max_body} chars]"
    data["body"] = {**(data.get("body") or {}), "content": body}
    return data


def list_folders() -> dict[str, Any]:
    """Mail folders (inbox, sent, archive, ...) with unread/total counts."""
    token = get_token()
    data = graph_get(token, "/me/mailFolders", {"$select": "id,displayName,totalItemCount,unreadItemCount"})
    return {"count": len(data.get("value", [])), "results": data.get("value", [])}


def summarize_messages(data: dict[str, Any], limit_rows: int = 15) -> str:
    msgs = (data.get("results") or [])[:limit_rows]
    lines = [f"messages: {data.get('count', len(msgs))} (showing {len(msgs)})"]
    for m in msgs:
        frm = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "?")
        lines.append(f"  {m.get('receivedDateTime', '?')[:10]} from={frm}")
        lines.append(f"    {m.get('subject', '(no subject)')}")
        if m.get("bodyPreview"):
            lines.append(f"    {m['bodyPreview'][:120]}")
    return "\n".join(lines)


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd = args[0]
    rest = args[1:]
    if cmd == "login":
        device_login()
    elif cmd == "folders":
        print(json.dumps(list_folders(), indent=2, default=str))
    elif cmd == "search":
        query, sender, since, top = None, None, None, 10
        i = 0
        while i < len(rest):
            if rest[i] == "--sender" and i + 1 < len(rest):
                sender = rest[i + 1]; i += 2
            elif rest[i] == "--since" and i + 1 < len(rest):
                since = rest[i + 1]; i += 2
            elif rest[i] == "--top" and i + 1 < len(rest):
                top = int(rest[i + 1]); i += 2
            elif rest[i] == "--json":
                i += 1  # summaries print by default; raw below covers it
            else:
                query = (query + " " + rest[i]).strip() if query else rest[i]; i += 1
        data = search_inbox(query, sender, since, top)
        if "--json" in rest:
            print(json.dumps(data, indent=2, default=str))
        else:
            print(summarize_messages(data))
    elif cmd == "read":
        if not rest:
            print("Usage: outlook.py read <message_id> [--max-body N] [--json]");
            sys.exit(2)
        max_body = 4000
        if "--max-body" in rest:
            max_body = int(rest[rest.index("--max-body") + 1])
        data = read_message(rest[0], max_body)
        if "--json" in rest:
            print(json.dumps(data, indent=2, default=str))
        else:
            frm = ((data.get("from") or {}).get("emailAddress") or {}).get("address", "?")
            print(f"Subject: {data.get('subject')}\nFrom: {frm}\nDate: {data.get('receivedDateTime')}\n")
            print((data.get("body") or {}).get("content", ""))
    else:
        print(f"Unknown command: {cmd}\n{__doc__}")
        sys.exit(1)


if __name__ == "__main__":
    main()
