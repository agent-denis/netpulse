# Contributing to NetPulse

Thanks for helping! Bug reports, ideas and pull requests are all welcome.

## Ground rules

- Be kind: this project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- Security problems go through [SECURITY.md](SECURITY.md), not public issues.
- By contributing you agree that your work is licensed under GPL-3.0-or-later.

## Development setup

```sh
sudo dnf install make python3 python3-pytest ruff rpm-build rpmlint \
    pyproject-rpm-macros python3-devel desktop-file-utils appstream
make run ARGS="--browser"   # run from the source tree
make test                   # offline test suite
make lint                   # ruff + licence headers + rpmlint
```

## Code rules

- **Runtime: Python standard library only.** No pip-only dependencies. The frontend is plain
  HTML, CSS and ES modules: no build step, no npm, no CDN, no web fonts.
- Type hints everywhere; `ruff check` and `ruff format` must pass.
- Every source file starts with an SPDX header in its comment syntax:
  ```
  SPDX-License-Identifier: GPL-3.0-or-later
  Copyright (C) <year> <your name>
  ```
- **Never use a shell.** Commands are built as argument lists from validated input
  (`src/netpulse/validators.py`). Values starting with `-` must be rejected.
- Render tool output with `textContent`; `innerHTML` and inline scripts/styles are not
  allowed (a test checks this).
- Show status with an icon or text as well as colour. New colours go in the token blocks at
  the top of `app.css`; the contrast test checks them in both themes.

## Adding a tool

1. Create `src/netpulse/tools/<name>.py` with `validate(params)`, `build_argv(params)`,
   `parse(output)` and a `TOOL = Tool(...)` entry, and add it to `MODULES` in
   `tools/__init__.py`.
2. Capture **real** outputs into `tests/fixtures/` (success, failure and timeout; IPv4 and
   IPv6 where it applies) and write tests for argv building, rejected input and parsing.
3. Create `src/netpulse/static/js/tools/<name>.js` with the form fields and a `render()`
   for the Summary view.

## Commits and pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
  `docs:`, …).
- Keep pull requests focused, add tests, and update `CHANGELOG.md` under *Unreleased*.
- CI (ruff, pytest, RPM build, rpmlint, desktop and AppStream validation) must be green.
