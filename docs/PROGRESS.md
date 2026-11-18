# NetPulse progress

| Phase | Status |
|---|---|
| 0 Scaffold | done |
| 1 Core backend (validators, security, jobs, server, history) | done |
| 2 UI shell (themes, cards, export, history dialog) | done |
| 3 Core tools: ping, traceroute/tracepath, dig, nslookup | done |
| 4 Extra tools (11 tools) | done |
| 5 Native GTK/WebKit window | done |
| 6 Packaging (spec, desktop, metainfo, icons, man page) | done |
| 7 GitHub files (README, CI, templates) | done |
| 8 Smoke test | done (2026-11-18) |

## Verified on Fedora 45 (2026-11-18)
- `make test` (496 tests) and `make lint` (ruff, headers, rpmlint 0 errors / 0 warnings) pass.
- `make rpm` and `make mock` (fedora-45-x86_64) build; `%check` runs the test suite.
- The RPM installs, runs (`netpulse --no-open`) and uninstalls completely in a clean mock chroot.
- Every tool ran in the UI against localhost, fedoraproject.org, 1.1.1.1 and an invalid
  host name, alternating Light and Dark; no JavaScript errors. Keyboard flow, Esc cancel,
  900 px layout, native window (snapshot, single instance, SIGTERM, export) checked.

## Waiting for the user
- `sudo dnf install ./build/rpmbuild/RPMS/noarch/netpulse-1.0.0-1.fc45.noarch.rpm`, then check that
  NetPulse shows up in GNOME Activities, launches, and `sudo dnf remove netpulse` cleans up.
- Fill in placeholders: `make set-author AUTHOR='…' YEAR=2026 EMAIL=…` (then commit).
- Push to GitHub (user does this), then CI runs for the first time.

## Known limitations / ideas
- mtr's JSON report only appears at the end (a progress bar shows meanwhile).
- With redirects, the HTTP timing shows "Redirects" vs "Final request" only (curl sums timers).
- Homoglyph check catches mixed-script labels, not whole-script look-alikes (all-Cyrillic).
- whois parsing is best effort; registries differ a lot (raw output always shown).
- The dev machine has no IPv6 internet: IPv6 success paths are tested with ::1 only.
- traceroute/mtr fixtures show this network's route (private hops + public ISP routers).
