# Extended checks: memory, systemd, TLS, log growth

Four additional read-only checks plug into the same contracts as the
built-in disk/environment checks: the `Operation`/`Workflow` safety model,
exit codes `0`/`1`/`2`, and deterministic JSON/CSV reporting (including the
CSV formula-injection defenses).

## Memory pressure

```bash
autoops memory --json --fail-on-warning
```

Reports `total_bytes`, `available_bytes`, `used_bytes`, `used_percent`, the
applied `warning_percent`, and `state` (`ok` / `warning`). The threshold
comes from the `memory_warning_percent` configuration key (default `90.0`).

Collection is platform-specific but dependency-free:

- Linux: `/proc/meminfo` (`MemTotal`, `MemAvailable`).
- macOS: `sysctl hw.memsize` plus `vm_stat` free/inactive/speculative pages.
- Windows: `GlobalMemoryStatusEx` via `ctypes`.

When memory information cannot be read, the check raises an operational
error (exit code 2) instead of reporting invented numbers.

## systemd service health

```bash
autoops systemd ssh.service --json --fail-on-warning
```

Reports `unit`, `active_state`, `sub_state`, `load_state`, and an aggregate
`state`: `active`, `inactive`, `failed`, `not-found`, or `unknown`.
`--fail-on-warning` returns exit code 1 for any state other than `active`.

Safety details:

- The unit name is validated strictly (no whitespace, control characters,
  path separators, or leading dashes) and passed to `systemctl` as a single
  argv element — never through a shell.
- Only `systemctl show` (a read-only query) is executed.
- If `systemctl` is missing or systemd is not running, the check fails with
  exit code 2 instead of guessing.

## TLS certificate expiry

```bash
autoops tls example.com --port 443 --warning-days 30 --json --fail-on-warning
```

Opens a TCP connection, performs a TLS handshake, and reads the leaf
certificate's expiry from the DER encoding with a small built-in parser
(no third-party ASN.1 library). Reports `host`, `port`, `not_after`
(UTC, `Z` suffix), `days_remaining`, the applied `warning_days`, and
`state` (`ok` / `warning` / `expired`).

Deliberate trade-offs, documented here so they are not surprises:

- Certificate **chain validation is disabled** (`CERT_NONE`). This check
  measures expiry only; it must not fail closed on trust configuration, and
  it never treats a host as "trusted" based on this handshake.
- Only the expiry timestamp is extracted; subject/issuer names are not
  parsed or reported.
- Connection, handshake, and parse failures are operational errors
  (exit code 2) with the remote host identified but no credential material
  in the message.

## Log-file growth

```bash
autoops loggrowth /var/log/app.log --interval-seconds 5 --max-bytes-per-second 1048576 --json --fail-on-warning
```

Samples the file size twice separated by `--interval-seconds` and reports
`size_bytes`, `previous_size_bytes`, `interval_seconds`, `growth_bytes`,
`growth_bytes_per_second`, the configured `max_bytes_per_second`, and
`state`:

- `ok`: growth within the configured maximum (or no maximum configured).
- `warning`: growth exceeded `--max-bytes-per-second`.
- `rotated`: the file shrank between samples (log rotation or truncation),
  reported distinctly instead of as negative growth.

The check only reads file metadata (`stat`); it never reads log contents.

## Exit codes and reporting

Like the built-in checks: exit `0` means the check completed and any
requested gate is healthy, `1` means the gate failed while the report was
still emitted, and `2` means invalid input or an operational error.
`--json` and `--csv` are mutually exclusive; CSV uses the same explicit
column schemas and formula-prefix neutralization as the existing reports.

## Programmatic use

Every check returns a dataclass with `to_dict()`, and
`autoops.operations.operation_from_check` wraps any such check as a
non-mutating `Operation` for workflow composition and audit logging:

```python
from autoops.checks import disk_status, memory_status
from autoops.operations import operation_from_check
from autoops.workflows import Workflow

workflow = Workflow(
    "node-health",
    (
        operation_from_check("memory", memory_status, 85.0),
        operation_from_check("disk", disk_status, "/"),
    ),
)
result = workflow.run()
```
