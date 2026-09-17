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

The aggregate result reports total, healthy, and unhealthy counts plus deterministic counts for `ok`, `stale`, `future`, and `undersized` states. Individual artifact results remain available in input order for support evidence and machine-readable reporting.

The check does not open, modify, delete, upload, or execute artifact contents. It reads filesystem metadata only. Missing or inaccessible paths raise their normal filesystem error instead of being silently converted into a healthy or incomplete summary.
