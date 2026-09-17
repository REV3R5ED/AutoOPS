# Artifact manifest health checks

`autoops-artifact` can assess several expected local outputs in one read-only run. This is useful when a scheduled job should produce a set of backups, exports, reports, or logs and operators need one deterministic health gate.

Create a JSON manifest:

```json
{
  "artifacts": [
    {"path": "backups/latest.tar", "max_age_seconds": 86400, "min_size_bytes": 1024},
    {"path": "reports/daily.json", "max_age_seconds": 7200, "min_size_bytes": 10}
  ]
}
```

Then run:

```bash
autoops-artifact --manifest artifacts.json --json --fail-on-unhealthy
```

Exit code `0` means every artifact met its freshness and size expectations, `1` means at least one artifact was stale, future-dated, or undersized, and `2` means the manifest or filesystem check could not be evaluated. JSON includes aggregate counts plus ordered per-artifact results. CSV emits one stable row per artifact.

The manifest schema is deliberately narrow. Each entry accepts only `path`, `max_age_seconds`, and optional `min_size_bytes`; unknown keys are rejected. AutoOPS does not execute commands from manifests, open artifact contents, upload files, or mutate the filesystem. Paths are assessed using local metadata only.
