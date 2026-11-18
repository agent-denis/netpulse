# Security policy

NetPulse runs network tools on your computer on behalf of a local web interface, so
security reports are taken seriously.

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report them privately through GitHub:
[Security → Report a vulnerability](https://github.com/agent-denis/netpulse/security/advisories/new).
If that is not possible, e-mail denis.solihull@pm.me.

Please include:

- the NetPulse version (`netpulse --version`) and your Fedora version,
- what an attacker can do and what they need (for example: another local user, a web page
  you visit, a malicious DNS answer),
- steps to reproduce, ideally a minimal proof of concept.

You will get an answer within 7 days. Once a fix is released you will be credited in the
changelog, unless you prefer not to be.

## What counts

Examples of issues we want to hear about:

- running a command or argument that the user did not ask for (argument or shell injection),
- reaching the local API without the token, or from another web page or origin,
- DNS rebinding, CSRF or XSS in the interface,
- tool output that is interpreted as HTML or script,
- processes that are left running after cancel, timeout or exit,
- reading or writing files outside NetPulse's own settings and history.

The network tests themselves send traffic to the hosts you enter; that is intended.
