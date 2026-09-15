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

## Operation safety contract

AutoOPS now has a reusable `Operation` / `OperationResult` contract for future automation modules. Every operation declares whether it mutates system state. Mutating operations default to **dry-run**, and their action is not called until a caller explicitly supplies `dry_run=False`.

Results use stable `success`, `status`, `message`, and `data` fields and serialize cleanly for CLI or integration output. Exceptions at the operation boundary are normalized into failed results rather than leaking inconsistent result shapes.

This contract is deliberately in place before state-changing modules are introduced so future features inherit safe behavior instead of adding safety later.

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
- [ ] configuration handling
- [x] dry-run framework
- [ ] structured logging
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

AutoOPS is intended for systems you own or administer with authorization. Current health-check functionality is read-only. The operation contract ensures future state-changing automation is dry-run by default and requires explicit operator intent before execution. Destructive or irreversible features should additionally provide feature-specific safeguards.

## Development

Changes should be useful, tested, documented, and suitable for a professional IT/cybersecurity portfolio.

## License

The package metadata currently declares MIT; a standalone LICENSE file will be added before the first stable release.
