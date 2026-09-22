# AutoOPS reviewer guide

This guide is a short evaluation path for recruiters, maintainers, and open-source reviewers who want to verify AutoOPS rather than only read its feature list.

## Five-minute evaluation

### 1. Install and run the tests

```bash
python -m pip install -e .
pytest -q
```

The project targets Python 3.10–3.13. CI also exercises Windows and macOS coverage and validates the built wheel before release.

### 2. Run a read-only operational preflight

```bash
autoops environment --json
autoops preflight . --json
```

These commands collect local environment and filesystem-health evidence without changing system state or probing remote hosts. The JSON form is intended to be stable enough for CI artifacts and support handoffs.

### 3. Verify an expected artifact

```bash
autoops-artifact ./README.md --min-size-bytes 100 --json --fail-on-unhealthy
```

This demonstrates a practical automation gate: assess whether an expected local artifact exists and meets explicit health criteria, emit machine-readable evidence, and expose deterministic exit semantics without modifying the artifact.

For a fuller end-to-end scenario, follow [the reproducible portfolio demo](portfolio-demo.md).

## Implementation areas worth inspecting

- **Health checks and CLI:** local, cross-platform operational diagnostics with human-readable and machine-readable output.
- **Operation safety contract:** state-changing operations are modeled explicitly and default to dry-run.
- **Workflow composition:** ordered operations preserve the same dry-run decision and fail-fast behavior rather than bypassing safeguards.
- **Structured audit logging:** operation results become newline-delimited JSON with recursive redaction for common secret-bearing fields.
- **Reporting:** deterministic JSON/CSV export, including spreadsheet-formula injection protection for string cells.
- **Artifact health:** manifest-driven checks reject malformed, ambiguous, or duplicate definitions instead of silently accepting them.

## Trust and safety boundaries

AutoOPS is designed for systems the operator owns or administers with authorization. Current health and artifact checks are local and read-only. There is no remote scanning, credential harvesting, persistence, exploitation, or destructive automation in the portfolio workflows.

Future state-changing operations must use the explicit operation contract: mutating operations are dry-run by default and require an affirmative caller decision to execute. Configuration is data-only JSON and does not execute code. Audit logging redacts common secret-bearing fields before serialization.

## What the project demonstrates

AutoOPS is intentionally small enough to review but structured like production automation: explicit safety semantics, stable result contracts, deterministic exit codes, portable reporting, tests across supported Python versions, package-build validation, and a guarded release path. The repository is currently preparing its first tagged portfolio release (`v0.3.0`); the README and release issue track that status rather than presenting an unpublished release as complete.
