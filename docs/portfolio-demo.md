# Reproducible portfolio demo

This short scenario demonstrates AutoOPS as a safe operations tool rather than a collection of isolated commands. Everything runs locally, performs read-only checks, and produces machine-readable evidence suitable for a CI artifact or support handoff.

## Scenario

An operator is about to start a maintenance window. Before making any changes, they want to verify that the workstation or runner has enough disk headroom, capture basic environment facts, and confirm that an expected backup/export artifact exists and is fresh.

## 1. Install the project

```bash
python -m pip install -e .
```

## 2. Capture a preflight report

```bash
autoops preflight . --json > preflight.json
```

The report combines local disk health and environment metadata. It does not probe remote systems or modify local state.

For a CI-style health gate, add an explicit disk threshold in `autoops.json`:

```json
{
  "disk_warning_percent": 90,
  "disk_min_free_gib": 2
}
```

Then run:

```bash
autoops --config autoops.json preflight . --json --fail-on-warning > preflight.json
```

Exit code `0` means the preflight is healthy, `1` means a configured warning threshold was reached, and `2` means the command could not complete because of invalid input, configuration, or another operational error. The JSON report is still emitted for a warning so diagnostic evidence can be retained.

## 3. Verify an expected artifact

Create a harmless local artifact to stand in for a backup or scheduled export:

```bash
mkdir -p demo-output
printf 'inventory snapshot\n' > demo-output/inventory.txt
```

Check that it is present, non-empty, and no more than one hour old:

```bash
autoops-artifact demo-output/inventory.txt \
  --max-age-seconds 3600 \
  --min-size-bytes 1 \
  --json \
  --fail-on-unhealthy > artifact-health.json
```

Exit code `0` means the assessed artifact is healthy, `1` means it was assessed but failed one or more health requirements, and `2` means the check itself was invalid or could not run.

## 4. Inspect the evidence

At this point the operator has two deterministic artifacts:

- `preflight.json` — environment and disk readiness evidence.
- `artifact-health.json` — freshness/size evidence for the expected local file.

Both outputs can be archived by CI, attached to a support ticket, or compared by downstream tooling. AutoOPS does not upload them or make any system change.

## Why this matters

The demo exercises the portfolio themes AutoOPS is designed to show: safe defaults, explicit failure semantics, observable operations, structured output, configuration validation, and practical automation that remains reviewable by an operator. It also demonstrates a credible real-world pattern: gather readiness evidence first, gate on known thresholds, and preserve diagnostics before a maintenance or deployment step begins.
