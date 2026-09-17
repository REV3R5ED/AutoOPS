# File freshness health check

`autoops freshness` is a local, read-only check for operational artifacts that are expected to be updated on a schedule, such as backup manifests, exports, heartbeat files, and generated reports.

```bash
autoops freshness /var/backups/latest.json --max-age-seconds 3600
autoops freshness ./heartbeat.txt --max-age-seconds 300 --json --fail-on-stale
```

The command reports the resolved path, file size, UTC modification timestamp, current age, configured maximum age, and an `ok`, `stale`, or `future` state. A `future` state means the file modification timestamp is later than the local reference clock. AutoOPS surfaces that condition instead of silently treating it as a fresh file, making clock skew, restored metadata, and timestamp anomalies visible to operators. `--json` and `--csv` provide machine-readable output through the same reporting layer as other AutoOPS checks.

Exit code `0` means the check completed successfully. With `--fail-on-stale`, exit code `1` means the artifact is unhealthy because it is either older than the configured threshold (`stale`) or carries a modification timestamp later than the local clock (`future`), while still preserving the report for CI or monitoring artifacts. Without the flag, both states remain diagnostic and return `0`. Exit code `2` indicates an invalid threshold, missing path, non-file path, or filesystem error.

Treating `future` as unhealthy when the gate is enabled prevents a clock-skewed artifact from satisfying a freshness SLO simply because its calculated age was clamped to zero. The existing flag name is retained for CLI compatibility.

## Safety

The check only reads filesystem metadata. It does not open, parse, modify, delete, upload, or transmit the target file. Directories are rejected so the freshness contract remains explicit, and thresholds must be finite non-negative numbers.
