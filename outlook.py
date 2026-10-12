#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""School Outlook inbox access via Microsoft Graph (read-only).

Auth: MSAL browser sign-in (authcode + PKCE loopback), delegated
``Mail.Read`` (plus ``User.Read`` on login so one grant also covers
OneDrive/SharePoint). No code typing — browser opens, sign in as
yourself, loopback captures grant.
Token cache lives OUTSIDE the repo (never committed; see .gitignore).

Setup (one time, no Azure registration needed):
  .venv/bin/python outlook.py login   # opens browser, sign in once
  .venv/bin/python outlook.py search "assignment" --top 5

By default the login tries two pre-consented first-party clients
(Microsoft Office, then Mozilla Thunderbird) and signs in as yourself —
no app registration, no admin consent. To force your own Entra app
instead: export INDUS_OUTLOOK_CLIENT_ID=<app (client) id>
[optional] export INDUS_OUTLOOK_AUTHORITY=https://login.microsoftonline.com/organizations
To disable the builtin chain: export INDUS_USE_BUILTIN_CLIENT=0.

If the school tenant blocks user consent entirely, an IT admin must
allow user consent for Mail.Read first (true for both custom and
builtin clients).
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
# First-party, pre-consented public clients — no app registration needed.
# Office is tried first (already consented in most school tenants),
# Thunderbird second (Mozilla's public client, same device-code flow).
BUILTIN_CLIENT_ID = "d3590ed6-52b3-4102-aeff-aad2292ab01c"
THUNDERBIRD_CLIENT_ID = "08162f7c-0fd2-4200-a84a-f25a4db0b584"
DEFAULT_AUTHORITY = "https://login.microsoftonline.com/common"
# One login covers mail + files: login requests all, silent calls use subsets.
ALL_SCOPES = ["User.Read", "Mail.Read", "Files.Read", "Sites.Read.All"]
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


def client_candidates() -> list[str]:
    """Client IDs to try, in order. Explicit app id wins; otherwise Office
    then Thunderbird. Set INDUS_USE_BUILTIN_CLIENT=0 to force explicit."""
    cid = (os.environ.get(CLIENT_ID_ENV) or "").strip()
    if cid:
        return [cid]
    if os.environ.get(BUILTIN_OPT_IN_ENV) == "0":
        raise RuntimeError(
            f"Set {CLIENT_ID_ENV} to your Entra app (client) id, or unset "
            f"{BUILTIN_OPT_IN_ENV}=0 to use the pre-consented builtin clients."
        )
    return [BUILTIN_CLIENT_ID, THUNDERBIRD_CLIENT_ID]


def _client_id() -> str:
    return client_candidates()[0]


CONSENT_RETRY_MARKERS = (
    "unauthorized_client",
    "invalid_client",
    "aadsts700016",
    "aadsts50020",
    "aadsts65002",
    "aadsts65001",
    "consent_required",
    "invalid_grant",
)

# Scope tiers: full first, then reduced. AADSTS65002 means client lacks
# preauthorization for some Graph permission — retry with fewer scopes.
SCOPE_TIERS = [
    ["User.Read", "Mail.Read", "Files.Read", "Sites.Read.All"],
    ["User.Read", "Mail.Read", "Files.Read"],
    ["User.Read", "Mail.Read"],
]


def _client_error_retryable(flow: dict[str, Any]) -> bool:
    blob = f"{flow.get('error', '')} {flow.get('error_description', '')}".lower()
    return any(s in blob for s in CONSENT_RETRY_MARKERS)


def _is_consent_retryable_msg(msg: str) -> bool:
    blob = (msg or "").lower()
    return any(s in blob for s in CONSENT_RETRY_MARKERS)


def build_app(client_id: str | None = None) -> msal.PublicClientApplication:
    cache = _load_cache()
    return msal.PublicClientApplication(
        client_id or _client_id(),
        authority=os.environ.get(AUTHORITY_ENV, DEFAULT_AUTHORITY),
        token_cache=cache,
    )


def browser_login(
    timeout: int = 120, scopes: list[str] | None = None
) -> dict[str, Any]:
    """Browser sign-in (no code typing). Tries Office then Thunderbird.

    Opens system browser to Microsoft sign-in; localhost loopback captures
    authcode + PKCE. Falls through to next client/scope-tier on
    unauthorized_client and AADSTS65002 (missing preauthorization).
    """
    last_err: str = ""
    tiers = [scopes] if scopes else []
    tiers += [t for t in SCOPE_TIERS if t != scopes]
    for cid in client_candidates():
        for tier in tiers:
            app = build_app(cid)
            print(f"[*] Graph client {cid} scopes={','.join(tier)} — opening browser…")
            try:
                result = app.acquire_token_interactive(
                    scopes=tier, prompt="select_account", timeout=timeout
                )
            except Exception as e:
                last_err = str(e)
                if _is_consent_retryable_msg(last_err):
                    continue
                raise RuntimeError(f"Login failed: {last_err}")
            if not result or "access_token" not in result:
                last_err = str((result or {}).get("error_description", result))
                if _is_consent_retryable_msg(last_err):
                    continue
                raise RuntimeError(f"Login failed: {last_err}")
            _save_cache(app.token_cache)
            account = (app.get_accounts() or [{}])[0]
            print(f"[+] Outlook login ok for {account.get('username', 'unknown')}")
            if tier != ALL_SCOPES:
                print(f"[!] Granted reduced scopes {tier}; rerun login for more.")
            return {"account": account.get("username"), "token_type": result.get("token_type")}
    raise RuntimeError(f"Browser login failed on all builtin clients: {last_err}")


def device_login(scopes: list[str] | None = None) -> dict[str, Any]:
    """Device-code login (fallback for headless). Tries Office then Thunderbird."""
    last_err: str = ""
    tiers = [scopes] if scopes else []
    tiers += [t for t in SCOPE_TIERS if t != scopes]
    for cid in client_candidates():
        for tier in tiers:
            app = build_app(cid)
            flow = app.initiate_device_flow(scopes=tier)
            if "user_code" not in flow:
                last_err = str(flow.get("error_description", flow))
                if _client_error_retryable(flow):
                    continue
                raise RuntimeError(f"Device flow failed: {last_err}")
            print(f"[*] Graph client {cid} scopes={','.join(tier)}")
            print(flow["message"])
            result = app.acquire_token_by_device_flow(flow)
            if "access_token" not in result:
                last_err = str(result.get("error_description", result))
                if _is_consent_retryable_msg(last_err):
                    continue
                raise RuntimeError(f"Login failed: {last_err}")
            _save_cache(app.token_cache)
            account = (app.get_accounts() or [{}])[0]
            print(f"[+] Outlook login ok for {account.get('username', 'unknown')}")
            return {"account": account.get("username"), "token_type": result.get("token_type")}
    raise RuntimeError(f"Device flow failed on all builtin clients: {last_err}")


def get_token(scopes: list[str] | None = None) -> str:
    """Silent token from cache (refreshes automatically). Tries each client."""
    want = scopes or SCOPES
    for cid in client_candidates():
        app = build_app(cid)
        accounts = app.get_accounts()
        if not accounts:
            continue
        result = app.acquire_token_silent(want, accounts[0])
        if result and "access_token" in result:
            _save_cache(app.token_cache)
            return result["access_token"]
    raise RuntimeError(
        "No Microsoft login. Run `python3 outlook.py login` first "
        "(no Azure app needed — builtin Office/Thunderbird clients)."
    )


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
        if "--device" in rest:
            device_login()
        else:
            browser_login()
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
