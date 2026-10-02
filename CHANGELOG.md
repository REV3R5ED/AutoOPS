# Changelog

All notable changes to AutoOPS are documented here. The project follows semantic versioning.

## [Unreleased]

### Added
- Remote/fleet checks: `autoops preflight ssh://[user@]host[:port]` runs read-only environment, disk, and memory probes on a remote host through the system `ssh` client and emits a schema-v5 preflight report (`docs/preflight-schema.md`, `docs/remote-checks.md`).
- Remote SSH checks use a strict host-key policy (`StrictHostKeyChecking=yes`, never auto-accept unknown keys), key-based auth only (`BatchMode=yes`, no password prompts), strict `ssh://` target validation that rejects option-flag smuggling, and an explicit allowlist of three read-only remote commands; remote checks plug into the `Operation`/`Workflow` contract via `autoops.remote.remote_check_operation`.
- New `autoops memory` check reporting host memory pressure (Linux `/proc/meminfo`, macOS `sysctl`/`vm_stat`, Windows `GlobalMemoryStatusEx`) with a configurable `memory_warning_percent` threshold (default `90.0`).
- New `autoops systemd <unit>` check reporting one systemd unit's health (`active`/`inactive`/`failed`/`not-found`/`unknown`) with strict unit-name validation and shell-free `systemctl` invocation.
- New `autoops tls <host>` check assessing remote TLS certificate expiry via a read-only handshake and a built-in DER parser (chain validation intentionally disabled; expiry only).
- New `autoops loggrowth <path>` check measuring a log file's short-term growth rate, distinguishing rotation (`rotated`) from excessive growth (`warning`).
- `autoops watch` daemon/sink mode: periodically runs read-only checks and appends redacted NDJSON audit events to an explicit `file:`, `syslog`, or `http(s)://` sink, with `--checks`, `--runs`, and `--interval-seconds` controls (see `docs/watch.md`).
- `autoops.operations.operation_from_check` wraps any `to_dict()`-style check as a non-mutating `Operation` for workflow composition and audit logging.
- Global `autoops --verbose` flag (and `verbose=True` on `Operation.run`/`Workflow.run`) reveals the exception detail suppressed by default at the operation boundary, for operator-initiated diagnostics.
- `ruff` (lint + format) and `mypy` checks in CI, plus an 80% coverage gate on the pytest run; new `dev` extra (`pip install -e .[dev]`) bundles `pytest`, `pytest-cov`, `ruff`, and `mypy`.
- `docs/preflight-schema.md` documents preflight report schema versions 1–5; `docs/remote-checks.md`, `docs/watch.md`, and `docs/extended-checks.md` document the new features.

### Changed
- Errors and diagnostics are now written to stderr instead of stdout, keeping machine-readable JSON/CSV output on stdout clean for CI consumers.
- The hardcoded `disk_warning_percent` default (`90.0`) is now the single `autoops.config.DEFAULT_DISK_WARNING_PERCENT` constant.

## [0.3.0] - 2026-09-18

### Added
- File freshness checks now report modification timestamps later than the reference clock as a distinct `future` anomaly instead of silently clamping them to a healthy zero-second age, making clock skew and restored-metadata anomalies visible in human, JSON, and CSV reports.
- CSV reporting now detects formula prefixes after Unicode whitespace (including non-breaking, em, narrow no-break, and ideographic spaces), closing a spreadsheet-formula bypass while preserving the original cell text.
- Workflow control flags now require real booleans: malformed `fail_fast` definitions and non-boolean workflow `dry_run` values are rejected before any operation executes, preventing loosely typed callers from silently changing workflow safety semantics.
- Operation safety flags now require real booleans: malformed `mutates_state` definitions and non-boolean `dry_run` values are rejected before any action executes, preventing loosely typed callers from accidentally authorizing state changes with values such as `0`.
- Workflows now reject blank/non-string names and non-`Operation` members at construction time, preventing ambiguous workflow identities and late runtime failures from malformed automation definitions.
- Operations now reject blank names and non-callable actions at construction time, preventing malformed automation definitions from reaching workflows or producing ambiguous audit/report identities.
- Operation result payloads now reject the reserved `operation` metadata key, preventing an action from spoofing its identity in serialized reports, logs, or workflow results.
- Numeric disk thresholds now reject non-finite values (`NaN` and positive/negative infinity), preventing malformed programmatic configuration from bypassing safety bounds or producing ambiguous health-check results.
- Workflows now reject an empty operation sequence at construction time, preventing configuration mistakes from being reported as successful automation runs when no checks or actions actually executed.
- Operation actions that accidentally return a non-dictionary value are now normalized into a stable failed `OperationResult` instead of raising during result assembly, preserving the operation boundary contract for future automation modules.
- Operation failures now suppress raw exception messages while retaining the operation name and exception type, preventing credentials, tokens, command output, paths, or other sensitive runtime details embedded in exceptions from leaking into serialized results, reports, or downstream logs.
- CSV reporting now neutralizes formula-like strings even when they are preceded by spaces, tabs, carriage returns, or newlines that spreadsheet applications may ignore before formula interpretation, closing a whitespace-prefix bypass while preserving the original cell text.
- CSV reporting now neutralizes string values beginning with common spreadsheet formula prefixes (`=`, `+`, `-`, `@`) so operator-controlled paths, hostnames, or future diagnostic text remain literal when exported reports are opened in spreadsheet applications.
- Disk and preflight health gates can now enforce an optional `disk_min_free_gib` threshold in addition to percentage-used limits. Machine-readable reports identify the threshold and warning reason, allowing operators to protect workloads that require a known amount of free capacity even on very large filesystems. The preflight report schema is now version `4` to make this additive contract change explicit.
- `autoops preflight` reports now include the running `autoops_version` in human, JSON, and CSV output so archived CI/support artifacts remain attributable to the exact tool version that produced them. The preflight report schema is now version `3` to make this additive contract change explicit.
- `autoops preflight` reports now expose a top-level `overall_state` in human, JSON, and CSV reports so CI and support tooling can consume one stable aggregate health signal without coupling to individual check fields. The preflight report schema is now version `2` to make this additive contract change explicit.
- `autoops preflight` reports now carry an explicit `schema_version` in human, JSON, and CSV output, giving downstream CI/support tooling a stable compatibility marker as the report evolves.
- `autoops preflight` reports now include a timezone-aware UTC `generated_at` timestamp in human, JSON, and CSV output so saved diagnostics remain attributable and useful as CI/support artifacts.
- `autoops preflight` combines local environment and disk health into one flat human, JSON, or CSV report for support handoffs and CI prechecks.
- `autoops preflight --fail-on-warning` preserves the diagnostic report while returning exit code 1 when the configured disk threshold is reached.
- `autoops disk --fail-on-warning` for CI and monitoring workflows that need a non-zero exit status when the configured disk threshold is reached, while preserving the selected human, JSON, or CSV report.

## [0.2.0] - 2026-09-15

### Added
- Reusable workflow composition with dry-run propagation and fail-fast behavior.
- Read-only environment health checks for host/runtime preflight diagnostics.
- Stable JSON and CSV reporting for disk and environment checks.
- Structured NDJSON audit logging with defense-in-depth redaction of common secret-bearing fields.
- Explicit JSON configuration with strict validation and safe defaults.
- Cross-platform CI coverage on Linux, Windows, and macOS.

### Changed
- Package and CLI version metadata aligned at `0.2.0`.
- Package metadata expanded for Python 3.10–3.13 and systems-administration use cases.

### Safety
- State-changing operations remain dry-run by default and require explicit operator intent to execute.
- Health checks are local and read-only; they do not probe remote systems.
- Logging never writes files implicitly and redacts common secret-bearing fields before serialization.

## [0.1.0]

### Added
- Initial Python package and CLI foundation.
- Common operation/result model and dry-run framework.
- Disk capacity health check.
- Unit tests and GitHub Actions CI.
