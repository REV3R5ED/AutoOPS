# Security Policy

## Supported versions

AutoOPS is currently in active pre-1.0 development. Security fixes are applied to the latest code on the `main` branch and will be included in subsequent tagged releases.

## Reporting a vulnerability

Please report suspected vulnerabilities through GitHub's private vulnerability reporting feature when it is available for this repository. Do not include secrets, credentials, private infrastructure details, or other sensitive production data in public issues.

If private vulnerability reporting is unavailable, open a public issue containing only a minimal, non-sensitive description that a security concern exists and request a private follow-up channel. Do not publish exploit details or confidential environment data.

A useful report includes the affected AutoOPS version or commit, operating system and Python version, the smallest safe reproduction steps, expected behavior, observed behavior, and the potential security or safety impact.

## Safety model

AutoOPS is designed around explicit operator control:

- Built-in health checks are local and read-only, except two explicit,
  narrowly scoped network features: `autoops tls` performs a single TLS
  handshake with the named host to read certificate expiry (chain validation
  disabled; expiry only, never a trust decision), and remote preflight runs
  three allowlisted read-only probes over SSH.
- Remote SSH checks never auto-accept unknown host keys
  (`StrictHostKeyChecking=yes`), use key-based auth only (`BatchMode=yes`),
  validate `ssh://` targets strictly, and refuse any command outside the
  read-only allowlist.
- `autoops watch` appends redacted audit events only to the sink the
  operator explicitly selects (file, syslog, or HTTP(S)); HTTP sink URLs
  with embedded credentials are rejected.
- Errors and diagnostics go to stderr so machine-readable JSON/CSV output
  on stdout stays clean for CI consumers.
- The global `--verbose` flag reveals exception detail suppressed by
  default; it is opt-in per invocation because the detail may include
  sensitive runtime data.
- Operations declare whether they mutate system state.
- Mutating operations default to dry-run and require an explicit `dry_run=False` decision before their action executes.
- Workflow composition preserves the operation-level dry-run decision instead of bypassing it.
- Configuration is data-only JSON and does not execute code.
- Structured audit logging redacts values associated with common secret-bearing field names before serialization.
- Output destinations are explicit; AutoOPS does not silently create audit-log files.

Future state-changing features should preserve these guarantees and add feature-specific validation, least-privilege guidance, bounded scope, and tests for failure behavior before release.

## Scope

Security reports are especially useful for issues that could cause an operation to execute despite dry-run mode, bypass an explicit safety gate, expose credentials or secret-bearing values, unexpectedly modify system state, execute configuration as code, or produce materially misleading health results that could lead to unsafe automation decisions.

General bugs and feature requests that do not have a security or safety impact should use the normal GitHub issue tracker.

## Responsible testing

Test AutoOPS only on systems and data you own or are explicitly authorized to administer. Use synthetic or non-sensitive data when demonstrating a problem. Do not use vulnerability research against third-party systems, and do not submit real credentials, access tokens, private keys, or production secrets in reports or test fixtures.
