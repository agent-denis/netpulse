# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-11-18

### Added

- Local web interface served on the loopback interface with a per-launch token,
  Host/Origin checks and a strict Content-Security-Policy.
- Native GTK 4 + WebKitGTK 6.0 window with single-instance handling; browser fallback,
  `--browser`, `--no-open`, `--port` and `--bind` options.
- Tools: ping (live RTT chart), traceroute with tracepath fallback, MTR, TCP port check,
  dig, nslookup, host, reverse DNS, resolver comparison, whois, HTTP(S) check with timing
  breakdown, TLS certificate, local network information, subnet calculator and quick
  diagnose.
- Live output over Server-Sent Events, cancelling, several jobs at once, Copy and export
  as TXT, JSON and Markdown.
- Searchable run history with re-run, clear and a size limit.
- Light (warm pastels), Dark and System themes with WCAG 2.1 AA contrast.
- RPM spec, desktop file, AppStream metainfo, icons, man page and Packit configuration.

[Unreleased]: https://github.com/agent-denis/netpulse/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/agent-denis/netpulse/releases/tag/v1.0.0
