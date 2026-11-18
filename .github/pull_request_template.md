## What does this change?

<!-- A short description, and the issue it fixes (e.g. "Fixes #12"). -->

## Checklist

- [ ] `make test` and `make lint` pass
- [ ] New or changed parsing is tested against **real** captured output in `tests/fixtures/`
- [ ] User input reaches commands only through `validators.py` (no shell, no leading `-`)
- [ ] UI: works with the keyboard, in light and dark themes, and status is not shown by colour alone
- [ ] New source files have the SPDX header
- [ ] `CHANGELOG.md` updated under *Unreleased*
