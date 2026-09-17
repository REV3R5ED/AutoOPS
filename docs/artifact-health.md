# Artifact health checks

Operational automation often needs stronger evidence than “the file exists.” A backup, export, report, or log can be freshly touched but empty or unexpectedly small.

`autoops.artifacts.artifact_health()` provides a local, read-only assessment that combines the existing freshness check with an explicit minimum-size expectation.

```python
from autoops.artifacts import artifact_health

status = artifact_health(
    "/var/backups/app.json",
    max_age_seconds=3600,
    min_size_bytes=1024,
)

if status.state != "ok":
    print(status.to_dict())
```

Installed packages also expose the same check as `autoops-artifact`, making it useful in shell scripts and CI without custom Python glue:

```bash
autoops-artifact /var/backups/app.json \
  --max-age-seconds 3600 \
  --min-size-bytes 1024 \
  --json \
  --fail-on-unhealthy
```

The command exits `0` for a healthy artifact, `1` when `--fail-on-unhealthy` is set and the artifact is stale, future-dated, or undersized, and `2` for invalid input or filesystem errors. JSON and CSV reports are still emitted before a health-gate exit code of `1`, so CI retains diagnostic evidence.

States are deterministic:

- `ok` — timestamp is healthy and the file meets the minimum size.
- `undersized` — timestamp is healthy but the file is smaller than expected.
- `stale` — the file is older than the allowed age.
- `future` — the modification timestamp is ahead of the reference clock.

Timestamp anomalies take precedence over size so a stale or clock-skewed artifact is not masked by a size warning. `min_size_bytes` defaults to `0`, preserving existence/freshness-only behavior unless an operator explicitly opts into a size expectation.

The check reads filesystem metadata only. It does not open, modify, upload, delete, or transmit the artifact, and it performs no remote probing. This makes it suitable as a building block for defensive CI prechecks, backup verification, export monitoring, and support diagnostics.
