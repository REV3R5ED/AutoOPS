# Batch artifact health

`autoops.artifacts.assess_artifacts()` provides a read-only way to verify several expected operational outputs in one pass. It is useful when a job is only healthy if multiple artifacts—such as a backup, export, and report—are all recent and non-trivially sized.

```python
from autoops.artifacts import ArtifactExpectation, assess_artifacts

result = assess_artifacts([
    ArtifactExpectation("backups/latest.tar", max_age_seconds=3600, min_size_bytes=1024),
    ArtifactExpectation("reports/status.json", max_age_seconds=900, min_size_bytes=2),
])

if not result.ok:
    print(result.to_dict())
```

The aggregate result reports total, healthy, and unhealthy counts plus deterministic counts for `ok`, `missing`, `stale`, `future`, and `undersized` states. Individual artifact results remain available in input order for support evidence and machine-readable reporting.

At least one expectation is required. An empty iterable raises `ValueError` instead of producing a vacuously healthy result, so library callers get the same fail-closed safety invariant as manifest-driven CLI checks.

Each expectation must also resolve to a unique local path. Duplicate spellings such as `backup.tar` and `./backup.tar` are rejected with `ValueError` rather than double-counting one artifact or applying conflicting thresholds to the same file. This mirrors the manifest CLI's uniqueness guarantee for direct library callers.

Constraint validation is independent of filesystem state: `max_age_seconds` must be a finite non-negative number and `min_size_bytes` must be a non-negative integer even when the expected artifact is currently missing. Invalid configuration therefore fails closed with `ValueError` instead of being masked as an ordinary `missing` health result.

The check does not open, modify, delete, upload, or execute artifact contents. It reads filesystem metadata only. A missing expected artifact is represented as an unhealthy `missing` state and the rest of the batch continues to be assessed; other filesystem errors are surfaced explicitly rather than being converted into ambiguous health results.
