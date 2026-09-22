# AutoOPS

Practical automation scripts and utilities for repetitive IT operations.

> Status: v0.3.0 release candidate — final tag pending

## Why AutoOPS

AutoOPS demonstrates production-minded IT automation rather than one-off scripts: read-only health checks, explicit exit semantics, deterministic JSON/CSV evidence, configurable safety thresholds, dry-run-by-default mutation contracts, workflow composition, and secret-aware audit logging. The fastest reviewer path is the **[reproducible portfolio demo](docs/portfolio-demo.md)**, which exercises a realistic local maintenance-readiness workflow without modifying the host or contacting remote systems.

## Goals

AutoOPS focuses on safe, understandable automation that reduces repetitive operational work while keeping actions observable and controllable.

Planned areas include system/environment checks, file maintenance workflows, service/process health checks, repeatable task runners, structured logging, dry-run support, and machine-readable output.

## Reproducible portfolio demo

For a recruiter-friendly end-to-end example, see **[Reproducible portfolio demo](docs/portfolio-demo.md)**. It walks through a local, read-only maintenance-readiness scenario that combines preflight health gating, artifact validation, explicit exit semantics, and JSON evidence suitable for CI or a support handoff.

## Health checks

AutoOPS provides cross-platform, read-only operational checks:

```bash
python -m pip install -e .
autoops disk .
autoops disk /path/to/check --json
autoops environment --json
autoops preflight .
autoops preflight /path/to/check --json --fail-on-warning
```

`disk` summarizes used/free filesystem capacity and warning state. `environment` captures a compact preflight snapshot containing hostname, operating system/release, machine architecture, Python version, and logical CPU count. `preflight` combines both checks into one flat report for support handoffs, CI prechecks, and repeatable workstation/server diagnostics. All three commands are local and read-only; none changes system state or probes remote hosts.

### Portfolio example: CI health gate

A deployment or maintenance pipeline can capture a complete local preflight report while treating disk pressure as a controlled warning failure:

```bash
autoops --config autoops.json preflight / --json --fail-on-warning > preflight.json
```

With disk thresholds configured, exit code `0` means the preflight is healthy, `1` means a disk threshold was reached, and `2` indicates an operational/configuration error. The report is still emitted for exit code `1`, so CI systems can retain diagnostic evidence as an artifact instead of losing context.

## Reporting and export

Health checks support human-readable output plus stable JSON and CSV reports. CSV uses explicit, deterministic column schemas so exports remain suitable for spreadsheets, inventory snapshots, CI artifacts, and downstream operational tooling. `--json` and `--csv` are mutually exclusive to prevent ambiguous output. Nested values are rejected by the CSV serializer instead of being silently flattened or losing structure. As a defense-in-depth measure, CSV string values beginning with common spreadsheet formula prefixes (`=`, `+`, `-`, `@`) are prefixed with an apostrophe so operator-controlled text remains literal when a report is opened in spreadsheet software.

## Configuration

AutoOPS supports an optional, explicit JSON configuration file. Pass it before the subcommand:

```bash
autoops --config autoops.json disk /
```

Example:

```json
{
  "json_output": true,
  "disk_warning_percent": 85,
  "disk_min_free_gib": 10
}
```

`json_output` changes the default output mode. `disk_warning_percent` warns when used capacity reaches the configured percentage. Optional `disk_min_free_gib` also warns when absolute free capacity falls below the configured GiB value; this is useful for workloads that need predictable headroom even on large filesystems. When both thresholds are configured, either condition can trigger a warning and reports identify the warning reason. Unknown keys, wrong types, malformed JSON, negative minimum-free values, and percentage thresholds outside 0–100 are rejected instead of being silently ignored. No config file is required; safe built-in defaults are used otherwise.

## Artifact health checks

`autoops-artifact` verifies that expected local files are present, fresh enough, and large enough without modifying them. It is useful for backup verification, scheduled export checks, evidence-collection pipelines, and CI jobs that need to fail when an expected artifact is stale or missing.

Check one file and emit machine-readable evidence:

```bash
autoops-artifact ./backup.tar.gz --max-age-seconds 86400 --min-size-bytes 1024 --json --fail-on-unhealthy
```

For repeatable checks, use a manifest. Relative artifact paths are resolved from the manifest location, which makes the same manifest portable across workstations and CI runners:

```json
{
  "artifacts": [
    {"path": "exports/inventory.json", "max_age_seconds": 3600, "min_size_bytes": 100},
    {"path": "backups/config.tar.gz", "max_age_seconds": 86400, "min_size_bytes": 1024}
  ]
}
```

```bash
autoops-artifact --manifest artifact-health.json --json --fail-on-unhealthy
```

Exit code `0` means the command completed and, when `--fail-on-unhealthy` is used, every artifact is healthy. Exit code `1` means at least one assessed artifact is unhealthy. Exit code `2` indicates invalid input, a malformed manifest, or an operational error. JSON and CSV output are available for automation; manifests reject unknown keys, invalid thresholds, empty artifact sets, and duplicate resolved paths instead of silently accepting ambiguous checks.

### Portfolio example: backup freshness gate

A scheduled backup job can run the manifest check after producing its files and retain the JSON result as an audit artifact. The gate is entirely local and read-only: AutoOPS checks metadata and size, but does not upload, delete, alter, or remotely probe anything. This demonstrates a practical operations pattern where automation produces both a deterministic decision and evidence that can be reviewed later.

## Operation safety contract

AutoOPS has a reusable `Operation` / `OperationResult` contract for automation modules. Every operation declares whether it mutates system state. Mutating operations default to **dry-run**, and their action is not called until a caller explicitly supplies `dry_run=False`.

Results use stable `success`, `status`, `message`, and `data` fields and serialize cleanly for CLI or integration output. Exceptions at the operation boundary are normalized into failed results rather than leaking inconsistent result shapes.

## Workflow composition

`autoops.workflows` composes operations into ordered, reusable workflows without bypassing their safety contract. Workflow execution passes a single dry-run decision to every step, so mutating steps remain non-executing by default. Workflows fail fast by default to avoid running dependent later steps after a failure; diagnostic workflows can explicitly disable fail-fast when collecting all results is more useful.

```python
from autoops.operations import Operation
from autoops.workflows import Workflow

workflow = Workflow(
    "preflight",
    (
        Operation("environment", lambda: {"ready": True}),
        Operation("planned-change", lambda: {"changed": True}, mutates_state=True),
    ),
)
result = workflow.run()  # planned-change is dry-run by default
```

`WorkflowResult.to_dict()` provides a stable machine-readable summary containing ordered step results and whether execution stopped early.

## Structured audit logging

`autoops.logging` turns `OperationResult` objects into stable, newline-delimited JSON audit events. Events include a timezone-aware UTC timestamp, event type, success/status fields, message, and operation data, making them suitable for later ingestion by monitoring or reporting tools.

The logger recursively redacts values stored under common secret-bearing field names such as passwords, tokens, API keys, secrets, and credentials before serialization. It never writes files implicitly: callers choose the destination stream, keeping logging behavior explicit and testable.

## Design Principles

- safe defaults
- idempotent operations where practical
- dry-run before destructive changes
- clear errors and audit-friendly output
- small, testable modules
- no embedded secrets

## Roadmap

### v0.1 — Foundation
- [x] Python package and CLI skeleton
- [x] common task/result model
- [x] configuration handling
- [x] dry-run framework
- [x] structured logging
- [x] initial safe operations module: disk health
- [x] unit tests and CI

### v0.2 — Operational Toolkit
- [x] reusable workflow composition
- [x] richer health checks
- [x] reporting/export support
- [x] improved cross-platform behavior

### Next — Release hardening
- [x] changelog and release notes
- [x] package metadata and release readiness review
- [x] portfolio-oriented usage examples
- [x] CI build and installed-wheel sanity coverage
- [ ] tagged portfolio release

## Related portfolio projects

AutoOPS is one part of a coordinated defensive IT/security portfolio:

- [LogLens](https://github.com/REV3R5ED/LogLens) — deterministic log analysis and explainable anomaly detection.
- [NetScope](https://github.com/REV3R5ED/NetScope) — bounded network visibility and diagnostics.
- [SentinelKit](https://github.com/REV3R5ED/SentinelKit) — Blue Team utilities for IOC, IP, hashing, and authentication-log triage.

Together the projects cover host/operations readiness, network diagnostics, log analysis, and SOC-oriented triage while keeping automation explicit, bounded, and defensive.

## Testing

```bash
python -m pip install -e . pytest
pytest -q
```

GitHub Actions runs the full test suite on Python 3.10–3.13 on Linux and adds Windows and macOS coverage on Python 3.12. CLI smoke tests exercise disk, environment, and combined preflight reporting. The release-sanity job path also builds both source and wheel distributions, installs the generated wheel, checks the packaged CLI version, and runs a packaged preflight command so packaging regressions are caught before tagging a release.

## Safety

AutoOPS is intended for systems you own or administer with authorization. Current health-check functionality is read-only and performs no remote probing. The operation and workflow contracts ensure future state-changing automation is dry-run by default and requires explicit operator intent before execution. Configuration is local and deliberately limited to documented keys; it does not load or execute code. Structured logging redacts common secret-bearing fields and writes only to streams explicitly supplied by the caller. Reporting only serializes already-collected result data and performs no system changes. Destructive or irreversible features should additionally provide feature-specific safeguards.

## Development

Changes should be useful, tested, documented, and suitable for a professional IT/cybersecurity portfolio.

## License

MIT. See [LICENSE](LICENSE).
