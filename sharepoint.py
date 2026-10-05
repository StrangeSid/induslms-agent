#!/usr/bin/env python3
"""School OneDrive / SharePoint access via Microsoft Graph (read-only).

Auth: same device-code flow + token cache as outlook.py (delegated,
read-only). Adds file scopes on top of mail — re-run login once after
upgrading scopes:
  export INDUS_OUTLOOK_CLIENT_ID=<app id>  # or INDUS_USE_BUILTIN_CLIENT=1
  python3 sharepoint.py login   # approve code in browser

Works on any OS (pure HTTPS; no OneDrive sync client or Mail.app needed).

CLI:
  python3 sharepoint.py login
  python3 sharepoint.py resolve <sharing-link>
  python3 sharepoint.py browse [path] [--site SITE_ID]
  python3 sharepoint.py sites [query]
  python3 sharepoint.py download <item-id-or-link> [--out DIR]
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from typing import Any, Optional

import outlook

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["Files.Read", "Sites.Read.All"]
DEFAULT_OUT_DIR = os.path.expanduser("~/Downloads/induslms")


def encode_sharing_url(url: str) -> str:
    """Pure: sharing URL -> Graph shares token (u! + unpadded base64url)."""
    raw = base64.b64encode(url.encode("utf-8")).decode("ascii")
    return "u!" + raw.rstrip("=").replace("/", "_").replace("+", "-")


def build_browse_path(path: str = "/", site_id: str | None = None) -> str:
    """Pure: (path, site) -> Graph children path for a folder listing."""
    p = (path or "/").strip()
    if site_id:
        base = f"/sites/{site_id}/drive/root"
    else:
        base = "/me/drive/root"
    if p in ("", "/"):
        return f"{base}/children"
    return f"{base}:/{p.strip('/')}:/children"


def device_login() -> dict[str, Any]:
    """Device-code login requesting file scopes (shares outlook's cache)."""
    import msal

    app = outlook.build_app()
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow failed: {flow.get('error_description', flow)}")
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    outlook._save_cache(app.token_cache)
    if "access_token" not in result:
        raise RuntimeError(f"Login failed: {result.get('error_description', result)}")
    print("[+] OneDrive/SharePoint login ok (scopes: Files.Read, Sites.Read.All)")
    return {"token_type": result.get("token_type")}


def get_token() -> str:
    """Silent file-scoped token. Re-login if the grant lacks file scopes."""
    import msal  # noqa: F401  (ensures dep present with a clear error)

    app = outlook.build_app()
    accounts = app.get_accounts()
    if not accounts:
        raise RuntimeError("No Microsoft login. Run `python3 sharepoint.py login` first.")
    result = app.acquire_token_silent(SCOPES, accounts[0])
    if not result or "access_token" not in result:
        raise RuntimeError(
            "No file access in the cached grant (scopes changed?). "
            "Run `python3 sharepoint.py login` again to consent."
        )
    outlook._save_cache(app.token_cache)
    return result["access_token"]


def graph_get(token: str, path: str, params: Optional[dict] = None) -> Any:
    url = f"{GRAPH_BASE}{path}"
    import requests

    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params=params,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def resolve_link(link: str) -> dict[str, Any]:
    """Resolve a OneDrive/SharePoint sharing link to driveItem metadata.

    Shared folders come back with their children ($expand) so one call
    is usually enough to see what's inside.
    """
    token = get_token()
    data = graph_get(
        token,
        f"/shares/{encode_sharing_url(link)}/driveItem",
        {"$expand": "children($top=100)"},
    )
    return data


def browse(path: str = "/", site_id: str | None = None) -> dict[str, Any]:
    """List a OneDrive folder (or a SharePoint default-drive folder)."""
    token = get_token()
    data = graph_get(
        token, build_browse_path(path, site_id), {"$top": 100, "$orderby": "name"}
    )
    return {"count": len(data.get("value", [])), "results": data.get("value", [])}


def list_sites(query: str | None = None) -> dict[str, Any]:
    """Find SharePoint sites (for the --site ID used by browse)."""
    token = get_token()
    params = {"search": query} if query else {"search": "*"}
    data = graph_get(token, "/sites", params)
    return {"count": len(data.get("value", [])), "results": data.get("value", [])}


def download(target: str, out_dir: str | None = None) -> dict[str, Any]:
    """Download a file by driveItem id or sharing link (read-only GETs).

    Returns {path, filename, size_bytes, content_type, url}.
    """
    import requests

    token = get_token()
    if out_dir is None:
        out_dir = DEFAULT_OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    if target.startswith("http"):
        meta = resolve_link(target)
        content_path = f"/shares/{encode_sharing_url(target)}/driveItem/content"
    else:
        meta = graph_get(token, f"/me/drive/items/{target}")
        content_path = f"/me/drive/items/{target}/content"
    name = meta.get("name") or target.rsplit("/", 1)[-1] or "download"
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    url = f"{GRAPH_BASE}{content_path}"
    r = requests.get(
        url, headers={"Authorization": f"Bearer {token}"}, timeout=60, stream=True
    )
    r.raise_for_status()
    path = os.path.join(out_dir, name)
    size = 0
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                size += len(chunk)
    return {
        "path": path,
        "filename": name,
        "size_bytes": size,
        "content_type": r.headers.get("content-type", ""),
        "url": url,
    }


def summarize_items(data: dict[str, Any], limit_rows: int = 20) -> str:
    items = (data.get("results") or data.get("children") or [])[:limit_rows]
    lines = [f"items: {data.get('count', len(items))} (showing {len(items)})"]
    for it in items:
        kind = "FOLDER" if "folder" in it else "FILE"
        lines.append(f"  [{kind}] {it.get('name')} (id={it.get('id')})")
    return "\n".join(lines)


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, rest = args[0], args[1:]
    if cmd == "login":
        device_login()
    elif cmd == "resolve":
        if not rest:
            print("Usage: sharepoint.py resolve <sharing-link>"); sys.exit(2)
        print(json.dumps(resolve_link(rest[0]), indent=2, default=str))
    elif cmd == "browse":
        path, site = "/", None
        i = 0
        while i < len(rest):
            if rest[i] == "--site" and i + 1 < len(rest):
                site = rest[i + 1]; i += 2
            else:
                path = rest[i]; i += 1
        data = browse(path, site)
        print(summarize_items(data) if "--json" not in rest
              else json.dumps(data, indent=2, default=str))
    elif cmd == "sites":
        q = rest[0] if rest and not rest[0].startswith("--") else None
        data = list_sites(q)
        if "--json" in rest:
            print(json.dumps(data, indent=2, default=str))
        else:
            for s in data.get("results", []):
                print(f"  {s.get('displayName')} (id={s.get('id')})")
    elif cmd == "download":
        if not rest:
            print("Usage: sharepoint.py download <item-id-or-link> [--out DIR]"); sys.exit(2)
        out = rest[rest.index("--out") + 1] if "--out" in rest else None
        result = download(rest[0], out)
        print(f"[+] Saved {result['filename']} ({result['size_bytes']} bytes)")
        print(f"    -> {result['path']}")
    else:
        print(f"Unknown command: {cmd}\n{__doc__}")
        sys.exit(1)


if __name__ == "__main__":
    main()
