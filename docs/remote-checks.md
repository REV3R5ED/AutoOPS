# Remote checks over SSH

AutoOPS can run its read-only health checks against remote hosts through the
operator's own `ssh` client:

```bash
autoops preflight ssh://deploy@web-01:2222 --json --fail-on-warning
```

The remote preflight collects environment, disk, and memory data from the
target and emits the [v5 preflight report](preflight-schema.md). It stays
inside the same safety contract as local checks: read-only collection,
explicit exit codes (`0` healthy, `1` gate failure, `2` operational error),
and deterministic JSON/CSV evidence.

## Target syntax

`ssh://[user@]host[:port]`

- `host` is a DNS name, IPv4 address, or bracketed IPv6 literal
  (`ssh://[2001:db8::1]`).
- `user` defaults to the local SSH user when omitted.
- `port` defaults to 22 when omitted.

Targets are validated strictly. Paths, query strings, whitespace, control
characters, and anything shaped like an ssh option flag (for example
`ssh://-oProxyCommand=...`) are rejected before any subprocess is started,
so a crafted target cannot smuggle extra arguments to the `ssh` command.

## Host-key policy: strict, never auto-accept

Remote checks run with `StrictHostKeyChecking=yes` and `BatchMode=yes`:

- The target host's key **must already be present** in the operator's
  `known_hosts` file. Unknown keys are never auto-accepted; the check fails
  with exit code 2 instead.
- Populate `known_hosts` out of band before first use, e.g. with one manual
  `ssh` connection (verifying the host key fingerprint through your normal
  channel) or `ssh-keyscan` followed by fingerprint verification.
- Authentication is key-based only. There are no password prompts and no
  credential handling: `BatchMode=yes` fails fast instead of asking.

## Command allowlist

Only three read-only probes may ever run on a remote host, and they are the
only commands this module will execute:

| Check         | Remote command                                        |
| ------------- | ----------------------------------------------------- |
| `disk`        | `df -kP -- <quoted-path>` (POSIX, machine-parseable)  |
| `environment` | `hostname`; `uname -s -r -m`; `nproc` (with fallbacks) |
| `memory`      | `grep -E '^(MemTotal\|MemAvailable):' /proc/meminfo`   |

Commands are passed to `ssh` as argv elements (never through a local shell).
The disk path argument is shell-quoted and must be absolute; anything else
is rejected. There is no generic "run this command" path: `run_remote_check`
raises `ValueError` for any check name outside the allowlist.

## Options

```bash
autoops preflight ssh://web-01 --ssh-timeout 10 --ssh-identity ~/.ssh/fleet_ed25519
```

- `--ssh-timeout` (default 15s, 1–300s): SSH connection timeout.
- `--ssh-identity`: private key file for key-based auth. The file must
  exist; it is passed to `ssh -i` and never read by AutoOPS itself.

Disk and memory warning thresholds come from the same configuration keys as
local checks (`disk_warning_percent`, `disk_min_free_gib`,
`memory_warning_percent`).

## Programmatic fleet use

`autoops.remote` exposes the pieces for fleet workflows:

```python
from autoops.remote import parse_ssh_target, remote_check_operation
from autoops.workflows import Workflow

targets = [parse_ssh_target("ssh://web-01"), parse_ssh_target("ssh://web-02")]
workflow = Workflow(
    "fleet-disk",
    tuple(remote_check_operation(target, "disk", "/") for target in targets),
    fail_fast=False,
)
result = workflow.run()  # read-only checks execute under default dry-run
```

Remote check operations are non-mutating, so they execute even under the
default dry-run decision, and their names embed the target label
(`remote-disk@web-01`) so audit events stay attributable per host. A failed
SSH connection or a failing host key check becomes a failed
`OperationResult` with the exception detail suppressed, exactly like local
operation failures.

## Limitations

- The memory probe reads `/proc/meminfo`: remote memory checks currently
  target Linux hosts. Other remote platforms fail the memory probe with a
  clear operational error rather than inventing numbers.
- Only key-based auth is supported. Hosts requiring passwords,
  keyboard-interactive, or certificate-specific flows are out of scope.
- Remote checks execute the system `ssh` client; if it is not installed,
  the check fails with exit code 2.
