# Contributing

Thanks for helping out. Small, focused PRs are easiest to review.

## Setup

```bash
git clone https://github.com/StrangeSid/induslms-agent.git
cd induslms-agent
./install.sh
```

`install.sh` handles the venv, dependencies, login, MCP configs, skill, and health check. If you prefer manual steps, see the README.

## Checks before a PR

```bash
source .venv/bin/activate
python -m pytest tests/ -q   # offline-safe: no network, no token needed
python -m build && python -m twine check dist/*  # packaging sanity
python lms.py doctor         # needs a valid login; reports issues, never raises
rm -rf dist build *.egg-info # don't commit build artifacts
```

- Keep MCP tools read-only. Never add login, mark-read, send, submit, or delete capabilities to `server.py`.
- Keep tool schemas small: no infra-only params (tenant is resolved server-side), bounded text outputs.
- New pure helpers (URL encoders, path builders, parsers) must come with offline unit tests — see `test_sharepoint_helpers_no_network`.
- Never commit `.env`, `*token*.json`, downloads, or personal data (emails, tenant IDs, absolute `/Users/...` paths). The test suite and review check for these.

## License

Contributions are accepted under the repo's dual license (**MIT or GPL-3.0-or-later**, see `LICENSE-MIT` and `COPYING`). By submitting a PR you agree your changes may be distributed under either license. New Python files should carry this header:

```python
# SPDX-License-Identifier: MIT OR GPL-3.0-or-later
```
