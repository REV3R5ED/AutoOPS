# AutoOPS

Practical automation scripts and utilities for repetitive IT operations.

> Status: early development / v0.1

## Goals

AutoOPS focuses on safe, understandable automation that reduces repetitive operational work while keeping actions observable and controllable.

Planned areas include system/environment checks, file maintenance workflows, service/process health checks, repeatable task runners, structured logging, dry-run support, and machine-readable output.

## Current capability: disk health

The first runnable module provides a cross-platform, read-only filesystem capacity check.

```bash
python -m pip install -e .
autoops disk .
autoops disk /path/to/check --json
```

Human output summarizes used/free capacity; `--json` produces a stable record suitable for scripts and monitoring integrations. Invalid paths fail explicitly without making system changes.

## Configuration

AutoOPS supports an optional, explicit JSON configuration file. Pass it before the subcommand:

```bash
autoops --config autoops.json disk /
```

Example:

```json
{
  "json_output": true,
  "disk_warning_percent": 85
}
```

`json_output` changes the default output mode and `disk_warning_percent` controls when the disk check reports a `warning` state. CLI `--json` can still opt into JSON for an individual invocation. Unknown keys, wrong types, malformed JSON, and thresholds outside 0–100 are rejected instead of being silently ignored. No config file is required; safe built-in defaults are used otherwise.

## Operation safety contract

AutoOPS has a reusable `Operation` / `OperationResult` contract for future automation modules. Every operation declares whether it mutates system state. Mutating operations default to **dry-run**, and their action is not called until a caller explicitly supplies `dry_run=False`.

Results use stable `success`, `status`, `message`, and `data` fields and serialize cleanly for CLI or integration output. Exceptions at the operation boundary are normalized into failed results rather than leaking inconsistent result shapes.

This contract is deliberately in place before state-changing modules are introduced so future features inherit safe behavior instead of adding safety later.

## Structured audit logging

`autoops.logging` turns `OperationResult` objects into stable, newline-delimited JSON audit events. Events include a timezone-aware UTC timestamp, event type, success/status fields, message, and operation data, making them suitable for later ingestion by monitoring or reporting tools.

The logger recursively redacts values stored under common secret-bearing field names such as passwords, tokens, API keys, secrets, and credentials before serialization. It never writes files implicitly: callers choose the destination stream, keeping logging behavior explicit and testable.

```python
from autoops.logging import write_json_event

with open("autoops.ndjson", "a", encoding="utf-8") as stream:
    write_json_event(result, stream)
```

Applications should still avoid placing sensitive material in operation results in the first place; redaction is a defense-in-depth safeguard, not a secret-management system.

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
- [ ] reusable workflow composition
- [ ] richer health checks
- [ ] reporting/export support
- [ ] improved cross-platform behavior

## Testing

```bash
python -m pip install -e . pytest
pytest -q
```

GitHub Actions runs the test suite and a CLI smoke test on Python 3.10–3.13.

## Safety

AutoOPS is intended for systems you own or administer with authorization. Current health-check functionality is read-only. The operation contract ensures future state-changing automation is dry-run by default and requires explicit operator intent before execution. Configuration is local and deliberately limited to documented keys; it does not load or execute code. Structured logging redacts common secret-bearing fields and writes only to streams explicitly supplied by the caller. Destructive or irreversible features should additionally provide feature-specific safeguards.

## Development

Changes should be useful, tested, documented, and suitable for a professional IT/cybersecurity portfolio.

## License

The package metadata currently declares MIT; a standalone LICENSE file will be added before the first stable release.
