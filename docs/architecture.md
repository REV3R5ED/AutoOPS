# AutoOPS architecture

This document gives reviewers and contributors a compact map of how AutoOPS turns local operational checks into deterministic, privacy-conscious evidence without hiding state changes behind automation.

## Design at a glance

AutoOPS separates collection, policy, orchestration, and presentation so each layer can be tested independently:

```text
operator / CI
    |
    +--> autoops CLI ------------------------+
    |       |                                |
    |       +--> config                      +--> reporting --> human / JSON / CSV
    |       +--> checks (disk, environment)  |
    |       +--> preflight aggregation ------+
    |
    +--> autoops-artifact CLI --> artifacts --> human / JSON / CSV

programmatic automation
    |
    +--> Operation --> Workflow --> OperationResult / WorkflowResult
                              |
                              +--> structured audit logging (NDJSON)
```

## Module responsibilities

| Module | Responsibility | Safety boundary |
| --- | --- | --- |
| `cli.py` | Main CLI, disk/environment/preflight commands, exit semantics | Local checks only; reporting is explicit |
| `checks.py` | Collect local disk and environment health | Read-only; no remote probing |
| `config.py` | Parse and validate documented JSON configuration | Rejects unknown/malformed values instead of guessing |
| `reporting.py` | Stable JSON/CSV serialization | Neutralizes spreadsheet-formula prefixes and rejects unsupported nested CSV values |
| `artifacts.py` | Evaluate expected files for presence, age, size, and timestamp anomalies | Reads metadata; does not modify artifacts |
| `artifact_cli.py` | Single-file and manifest artifact-health interface | Explicit exit codes and machine-readable evidence |
| `operations.py` | Reusable operation/result contract | State-changing operations are dry-run by default |
| `workflows.py` | Ordered operation composition and fail-fast behavior | Propagates one explicit dry-run decision through all steps |
| `logging.py` | NDJSON audit-event serialization | Redacts common secret-bearing fields; caller owns the output stream |

## Two execution paths

### Read-only diagnostics

The `autoops` and `autoops-artifact` CLIs are intended for support, CI prechecks, backup/export validation, and maintenance-readiness evidence. Collection happens locally, results are normalized, and the caller chooses human, JSON, or CSV output. Warning-aware flags can turn an unhealthy result into a non-zero exit code without suppressing the diagnostic report.

This path does not use the mutation framework because its current checks do not change host state.

### Reusable automation contract

`Operation` is the boundary for programmatic automation. An operation declares whether it mutates state. A mutating operation does not execute its action unless the caller explicitly opts out of dry-run. `Workflow` composes validated operations and propagates that dry-run decision consistently, with fail-fast enabled by default.

This separation is intentional: future automation can reuse the operation/workflow contract without weakening the safety guarantees of the read-only diagnostic commands.

## Evidence and failure semantics

AutoOPS treats output as operational evidence rather than decoration:

- JSON and CSV schemas are deterministic for downstream automation.
- Preflight reports include schema/version and generation metadata for attribution.
- Health gates preserve reports when returning a warning failure.
- Artifact checks distinguish missing, stale, undersized, and future-timestamp conditions.
- Operation exceptions are normalized at the boundary rather than leaking arbitrary result shapes.
- Audit logging recursively redacts common secret-bearing fields before serialization.

CLI exit codes follow a simple contract where supported: `0` means the command completed successfully and the requested gate is healthy, `1` means a completed health assessment failed its requested gate, and `2` represents invalid input or an operational/configuration error.

## Trust boundaries

AutoOPS deliberately does **not** treat configuration, report data, or manifests as executable instructions. Configuration is limited to documented keys. Artifact manifests describe local files and thresholds. Current health checks perform no network discovery or remote execution. Logging writes only to a stream explicitly supplied by the caller.

The repository's `SECURITY.md` defines vulnerability-reporting expectations; the README documents the operator-facing safety contract.

## Extension checklist

A new feature should preserve these boundaries:

1. Decide whether it is a read-only check or a state-changing operation.
2. Validate input before performing work; reject ambiguous types and unknown fields.
3. Keep collection separate from formatting and policy where practical.
4. For mutations, use explicit operator intent and dry-run by default.
5. Define stable result and exit semantics before adding integrations.
6. Avoid placing secrets or raw exception details in reports/logs.
7. Add unit tests for success, boundary conditions, malformed input, and safety behavior.
8. Add CLI/integration coverage when the public contract changes.
9. Update README/changelog documentation when user-visible behavior changes.

## Reviewer path

For a concrete end-to-end scenario, continue with [`portfolio-demo.md`](portfolio-demo.md). For implementation details, start with `src/autoops/cli.py` for the read-only diagnostic path and `src/autoops/operations.py` plus `src/autoops/workflows.py` for the reusable automation safety contract.
