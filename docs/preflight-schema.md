# Preflight report schema versions

`autoops preflight` emits a flat report (human, JSON, or CSV) carrying an
explicit integer `schema_version`. Downstream CI and support tooling should
key compatibility decisions off this field rather than on the AutoOPS
version, because report shape and tool version evolve independently.

Schema versions are append-only: a new version adds fields but never removes
or renames existing ones.

## Version history

### v1 — initial schema marker
- `schema_version`, `generated_at` (timezone-aware UTC, `Z` suffix).
- Local environment fields: `hostname`, `platform`, `platform_release`,
  `architecture`, `python_version`, `cpu_count`.
- Local disk fields: `disk_path`, `disk_total_bytes`, `disk_used_bytes`,
  `disk_free_bytes`, `disk_used_percent`, `disk_state`, `disk_warning_reason`,
  `disk_warning_percent`, `disk_min_free_gib`.

### v2 — aggregate health signal
- Added `overall_state`: a single top-level aggregate (`ok` / `warning`)
  mirroring the disk state, so consumers do not need to couple to
  individual check fields.

### v3 — tool attribution
- Added `autoops_version`: the exact AutoOPS version that produced the
  report, so archived CI/support artifacts remain attributable.

### v4 — absolute free-capacity threshold
- `disk_min_free_gib` became a first-class configured threshold alongside
  `disk_warning_percent`; `disk_warning_reason` can now report
  `used_percent`, `min_free_gib`, or both (comma-separated).

### v5 — remote preflight (`autoops preflight ssh://[user@]host[:port]`)
Remote preflight reuses the v1–v4 local fields where they are collectible
over the read-only SSH probes, and adds:

- `remote_host`: the validated `[user@]host[:port]` target label.
- `memory_total_bytes`, `memory_used_bytes`, `memory_used_percent`,
  `memory_state`, `memory_warning_percent`: remote memory pressure from the
  remote host's `/proc/meminfo` (Linux remotes).
- `python_version` is `null`: the remote probes do not collect the remote
  Python version.
- `overall_state` is `warning` when either the remote disk or the remote
  memory check reaches its warning threshold.

## Compatibility notes

- Consumers should ignore unknown fields to stay forward-compatible.
- `disk_warning_reason` is an empty string (not null) when the state is `ok`.
- `disk_min_free_gib` and `cpu_count` are `null` when unconfigured or
  unavailable; CSV renders them as empty cells.
- All byte counts are integers; percentages are floats rounded to two
  decimals; timestamps use the `Z` suffix form of ISO-8601 UTC.
