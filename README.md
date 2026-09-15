# AutoOPS

Practical automation scripts and utilities for repetitive IT operations.

> Status: active development / v0.2

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
- [x] reusable workflow composition
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

AutoOPS is intended for systems you own or administer with authorization. Current health-check functionality is read-only. The operation and workflow contracts ensure future state-changing automation is dry-run by default and requires explicit operator intent before execution. Workflows fail fast by default, reducing the chance that dependent later actions run after an unsuccessful prerequisite. Configuration is local and deliberately limited to documented keys; it does not load or execute code. Structured logging redacts common secret-bearing fields and writes only to streams explicitly supplied by the caller. Destructive or irreversible features should additionally provide feature-specific safeguards.

## Development

Changes should be useful, tested, documented, and suitable for a professional IT/cybersecurity portfolio.

## License

MIT. See [LICENSE](LICENSE).
