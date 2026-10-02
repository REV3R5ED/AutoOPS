# `autoops watch`: periodic checks with audit sinks

`autoops.logging` has always been able to turn `OperationResult` objects
into redacted NDJSON audit events — but nothing in the CLI wrote those
events anywhere. `autoops watch` closes that loop: it runs a set of
read-only checks on an interval and appends one redacted audit event per
check per iteration to an explicit sink.

```bash
autoops watch --interval-seconds 300 --sink file:/var/log/autoops/audit.ndjson --runs 12
```

## Sinks

The sink is an explicit operator choice; selecting a destination is the
intent to write there. Three sink types are supported:

| Spec                        | Destination                                              |
| --------------------------- | -------------------------------------------------------- |
| `file:<path>`               | Append NDJSON lines to a local file (created if missing) |
| `syslog`                    | System log via `/dev/log`, else UDP `127.0.0.1:514`      |
| `syslog:<address>`          | System log via `/path/to/socket` or `host:port`          |
| `http(s)://<url>`           | POST each event as `application/x-ndjson`                |

Examples:

```bash
autoops watch --sink file:./audit.ndjson --runs 1 --interval-seconds 60
autoops watch --sink syslog --checks disk,memory
autoops watch --sink https://logs.example.com/ingest --interval-seconds 60
```

Sink rules:

- HTTP(S) URLs with embedded credentials (`http://user:pass@host/`) are
  rejected rather than sent.
- A sink that cannot be opened or written to ends the run with exit code 2
  and a diagnostic on stderr.
- Events are flushed after every write, so a killed watcher loses at most
  the in-flight iteration.

## Checks and options

- `--checks`: comma-separated subset of `disk`, `environment`, `memory`
  (default: all three). Unknown names are rejected with exit code 2.
- `--path`: path inspected by the disk check (default: `.`).
- `--interval-seconds`: seconds between iterations (default: 300).
- `--runs`: number of iterations; `0` (default) runs until interrupted
  with Ctrl-C, which stops cleanly with exit code 0.
- `--verbose`: reveal suppressed exception details in failure events
  (see below).

Memory warning thresholds come from the `memory_warning_percent`
configuration key, like the `memory` command.

## Events

Each iteration runs the checks through a non-fail-fast `Workflow`, so one
failing check does not suppress the remaining checks' events. Every event
is built with `autoops.logging.build_audit_event`, which means:

- timezone-aware UTC timestamps,
- stable `event` / `success` / `status` / `message` / `data` fields,
- recursive redaction of common secret-bearing field names before
  serialization.

Operations that declare `mutates_state` are rejected: watch is a read-only
loop, and a mutating operation is a configuration error (exit code 2).

## Diagnostics and the `--verbose` knob

Progress lines (`watch: iteration 3: wrote 3 audit event(s)`) and all error
diagnostics go to **stderr**, so stdout stays clean and any redirection of
event data is unambiguous. (File/HTTP/syslog sinks never use stdout at
all.)

By default, check failures in watch carry the same suppressed exception
detail as everywhere else in AutoOPS. Passing the global `--verbose` flag
opts into full exception detail in the failure events for that run:

```bash
autoops --verbose watch --sink file:./audit.ndjson --runs 1
```

Verbose output may include paths, hostnames, command output, or other
sensitive runtime details — that is why it is opt-in per invocation and
never the default for unattended runs.
