# CLAUDE.md: NetPulse

Local, single-user network diagnostics GUI for Fedora. A Python stdlib backend
runs real system tools and streams their output over SSE to a vanilla
HTML/CSS/JS frontend. The frontend runs in a GTK4/WebKitGTK 6 window or the
default browser.

Progress and the next steps are in `docs/PROGRESS.md`. Read it first when resuming.

## Commands
| Command | What it does |
|---|---|
| `make run ARGS="--browser"` | run from the source tree (`PYTHONPATH=src python3 -m netpulse`) |
| `make test` | offline pytest suite (network tests skipped) |
| `make test-network` | also runs tests marked `@pytest.mark.network` |
| `make lint` | ruff check + ruff format --check + SPDX header check + rpmlint |
| `make tarball` / `srpm` / `rpm` | `git archive HEAD` → rpmbuild with `_topdir=build/rpmbuild` |
| `make mock` | clean build in mock for the current Fedora |
| `make set-author AUTHOR='Name' YEAR=2026` | replace the `<AUTHOR>`/`<YEAR>` placeholders |

`make tarball` uses `git archive HEAD`, so **commit before building RPMs**.

## Conventions
- Python ≥ 3.12, **standard library only at runtime**. Type hints everywhere, ruff-clean
  (`pyproject.toml` has the rule set). Run `ruff format` on the code.
- Every source file starts with `SPDX-License-Identifier: GPL-3.0-or-later` +
  `Copyright (C) <YEAR> <AUTHOR>` (`tests/check_headers.py` enforces it).
- Conventional Commits. Repo-local identity: `Denis <356570572+agent-denis@users.noreply.github.com>`.
  **Never push**: the user pushes to GitHub themselves.
- Placeholders that stay as they are: `<AUTHOR>`, `<YEAR>`. GitHub user is `agent-denis`
  (approved by the user), App ID `io.github.agent-denis.NetPulse`.
- Each tool is a module in `src/netpulse/tools/` that exposes `build_argv(params) -> list[str]` and
  `parse(output) -> dict` (see `tools/base.py`). Parsers are tested against real captured
  outputs in `tests/fixtures/`.
- Frontend: ES modules, no build step, no CDN, no inline script/style (strict CSP).
  Tool output is rendered with `textContent` only.
- Status is never shown by colour alone: always add an icon or text too.

## Security model (hard requirements, see SECURITY.md)
- Bind to 127.0.0.1 only. Random port unless `--port`. Non-loopback addresses are refused.
- Random per-launch token required on every `/api/*` request: `X-NetPulse-Token` header,
  or the `token` query parameter for EventSource (SSE can't send headers). The comparison is
  constant-time.
- `Host` must be `127.0.0.1:<port>` or `localhost:<port>`. When `Origin` is present, it must
  match. This blocks DNS rebinding and cross-site requests.
- `subprocess` with an argv list only, `shell=False`. Inputs are validated server-side
  (`validators.py`): values starting with `-` are rejected, and `--` goes before positional
  arguments where the tool supports it.
- Jobs: own process group (`start_new_session=True`), timeout, output cap, concurrency cap.
  The whole group is killed on cancel, timeout, client disconnect or shutdown.

## Decisions
- LICENSE copied from `/usr/share/licenses/coreutils-common/COPYING`
  (sha256 = gnu.org gpl-3.0.txt, checked by a test).
- The theme anti-flash script is the external `static/js/theme-init.js`, loaded without
  `defer` (CSP forbids inline scripts).
- Homoglyphs: IDN names are allowed, but a label that mixes scripts (e.g. Latin+Cyrillic)
  is rejected. The UI shows the punycode form.
- `dig ANY` is kept, with a note about RFC 8482 minimal answers.
- traceroute defaults to UDP mode (no root). ICMP/TCP modes are offered with a note that
  they need privileges. sudo/pkexec are never called.
