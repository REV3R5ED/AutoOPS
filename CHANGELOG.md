# Changelog

All notable changes to AutoOPS are documented here. The project follows semantic versioning.

## [Unreleased]

### Added
- Workflows now reject an empty operation sequence at construction time, preventing configuration mistakes from being reported as successful automation runs when no checks or actions actually executed.
- Operation actions that accidentally return a non-dictionary value are now normalized into a stable failed `OperationResult` instead of raising during result assembly, preserving the operation boundary contract for future automation modules.
- Operation failures now suppress raw exception messages while retaining the operation name and exception type, preventing credentials, tokens, command output, paths, or other sensitive runtime details embedded in exceptions from leaking into serialized results, reports, or downstream logs.
- CSV reporting now neutralizes formula-like strings even when they are preceded by spaces, tabs, carriage returns, or newlines that spreadsheet applications may ignore before formula interpretation, closing a whitespace-prefix bypass while preserving the original cell text.
- CSV reporting now neutralizes string values beginning with common spreadsheet formula prefixes (`=`, `+`, `-`, `@`) so operator-controlled paths, hostnames, or future diagnostic text remain literal when exported reports are opened in spreadsheet applications.
- Disk and preflight health gates can now enforce an optional `disk_min_free_gib` threshold in addition to percentage-used limits. Machine-readable reports identify the threshold and warning reason, allowing operators to protect workloads that require a known amount of free capacity even on very large filesystems. The preflight report schema is now version `4` to make this additive contract change explicit.
- `autoops preflight` reports now include the running `autoops_version` in human, JSON, and CSV output so archived CI/support artifacts remain attributable to the exact tool version that produced them. The preflight report schema is now version `3` to make this additive contract change explicit.
- `autoops preflight` now exposes a top-level `overall_state` in human, JSON, and CSV reports so CI and support tooling can consume one stable aggregate health signal without coupling to individual check fields. The preflight report schema is now version `2` to make this additive contract change explicit.
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
