# Security Policy

## Supported Versions

The `main` branch is the only supported version.

| Version | Supported |
| ------- | ----------|
| main    | Yes       |
| Any tagged release | Best-effort |

## Reporting a Vulnerability

If you believe you've found a security issue in the Excalidraw Diagram Skill,
**please do not open a public GitHub issue**. Instead, use the private
advisory channel:

- Open a GitHub Security Advisory at
  https://github.com/welshofer/excalidraw-diagram-skill/security/advisories/new
- Or email the maintainer (preferred for urgent issues): see the GitHub
  profile of the repository owner.

We aim to acknowledge reports within **72 hours** and publish a fix or
mitigation plan within **90 days** of the initial report. Researchers who
follow the disclosure timeline will be credited in the release notes.

## What We Care About

The following classes of issue are in scope:

- **Remote code execution via crafted `.excalidraw` JSON**. The render
  pipeline loads an Excalidraw bundle in headless Chromium; any payload
  that escapes the sandbox or causes arbitrary code execution on the host
  is a serious issue.
- **Path traversal / arbitrary file writes**. The render script validates
  output paths but the renderer is a privileged tool on the developer's
  machine -- writes outside intended directories are in scope.
- **SSRF via the `link` element property**. The template currently loads
  external content only from `esm.sh`; an attacker who can coerce the
  browser into fetching from other origins or exfiltrating data is in
  scope.
- **Server-mode CSRF / missing auth**. The render server listens on
  localhost; attacks from malicious local processes (including other user
  accounts on multi-tenant machines) are in scope.
- **Supply-chain issues with the vendored bundle**. If the vendored bundle
  in `references/vendor/excalidraw-bundle.js` diverges from the upstream
  Excalidraw release, or the integrity check can be bypassed, report it.

## Out of Scope

- Issues that require a pre-authenticated attacker on the machine running
  the tool. The tool assumes the local user is trusted.
- Crashes in the validator that result from malformed but well-intentioned
  input (open an issue instead).
- Denial of service via pathologically large diagrams -- the validator
  enforces a `--max-elements` cap and the server enforces a body-size
  limit. Report bypasses of those caps.

## Hardening Notes

Security hardening in the current codebase:

- The HTML template uses a nonce-based CSP (`strict-dynamic`, no
  `'unsafe-inline'`) and the vendor bundle is loaded from a `blob:` URL.
- The render server rejects cross-origin POSTs, enforces `Host:` header,
  caps POST body size, and supports `--auth-token` Bearer auth.
- The validator blocks `javascript:`, `data:`, `vbscript:` link schemes
  and protocol-relative URLs (`//evil.com`).
- Symlink cycles are rejected at `validate_path` time via `os.stat`.
- The vendor bundle has SHA-256 + SRI integrity data stored alongside it
  and is verified on each render.
