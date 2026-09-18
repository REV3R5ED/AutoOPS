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

Relative artifact paths are resolved from the manifest file's directory, not from the process working directory. This makes a manifest portable as a self-contained operations bundle and prevents a scheduler, CI runner, or service launched from another directory from accidentally checking the wrong relative path. Absolute artifact paths remain unchanged.

The `artifacts` array must contain at least one entry. AutoOPS rejects an empty manifest with exit code `2` instead of reporting a vacuous healthy result, preventing a misconfigured scheduled health gate from silently succeeding without checking anything.

Each resolved artifact path must be unique within a manifest. AutoOPS rejects duplicate references, including equivalent spellings such as `backup.json` and `./backup.json`, instead of double-counting one file with potentially conflicting thresholds. This keeps aggregate health totals trustworthy and makes configuration mistakes explicit with exit code `2`.

`max_age_seconds` must be a finite, non-negative number. Non-finite values such as `NaN` or positive/negative infinity are rejected with exit code `2` so malformed JSON produced by permissive serializers cannot silently disable or distort freshness enforcement.

Exit code `0` means every artifact met its freshness and size expectations, `1` means at least one artifact was missing, stale, future-dated, or undersized, and `2` means the manifest or another filesystem check could not be evaluated. JSON includes aggregate counts plus ordered per-artifact results. CSV emits one stable row per artifact.

A missing expected path is a health result rather than a batch-processing error. It is reported with state `missing` and null size/timestamp/age metadata, and AutoOPS continues evaluating later entries. This makes a manifest useful as a complete scheduled-job health report even when one expected backup or export was never produced. Other filesystem errors remain explicit errors rather than being silently converted to health states.

The manifest schema is deliberately narrow. Each entry accepts only `path`, `max_age_seconds`, and optional `min_size_bytes`; unknown keys are rejected. AutoOPS does not execute commands from manifests, open artifact contents, upload files, or mutate the filesystem. Paths are assessed using local metadata only.
