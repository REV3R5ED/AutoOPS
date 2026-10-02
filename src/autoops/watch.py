"""Periodic check runner that persists redacted NDJSON audit events.

``autoops.watch`` exists because :mod:`autoops.logging` emits audit events but
nothing in the CLI wrote them anywhere. Watch runs a set of read-only checks
on an interval, converts each :class:`~autoops.operations.OperationResult`
into a redacted audit event with :func:`autoops.logging.build_audit_event`,
and appends the events to an explicit sink: a local file, syslog, or an HTTP
endpoint.

Sinks are explicit operator choices: selecting a destination is the intent to
write there. Watch itself performs no state changes beyond appending audit
events to the chosen sink. Progress and diagnostics go to stderr so piped or
redirected event streams stay clean.
"""

from __future__ import annotations

import contextlib
import json
import logging.handlers
import socket
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from autoops.logging import build_audit_event
from autoops.operations import Operation
from autoops.workflows import Workflow

_DEFAULT_INTERVAL_SECONDS = 300.0
_HTTP_TIMEOUT_SECONDS = 10.0


class SinkError(OSError):
    """Raised when an audit sink cannot be opened or written to."""


class Sink:
    """Destination for NDJSON audit events."""

    def write_event(self, event: dict[str, Any]) -> None:
        raise NotImplementedError

    def close(self) -> None:
        """Release sink resources. Called once when watch stops."""


class FileSink(Sink):
    """Append NDJSON audit events to a local file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        if not str(self.path):
            raise SinkError("file sink path must not be empty")
        try:
            self._handle = self.path.open("a", encoding="utf-8")
        except OSError as exc:
            raise SinkError(f"could not open audit file {self.path}: {exc}") from exc

    def write_event(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
        try:
            self._handle.write(line)
            self._handle.flush()
        except OSError as exc:
            raise SinkError(f"could not write audit event to {self.path}: {exc}") from exc

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._handle.close()


class SyslogSink(Sink):
    """Forward NDJSON audit events to syslog via the stdlib SysLogHandler."""

    def __init__(self, address: str | None = None) -> None:
        if address is None:
            default = "/dev/log" if Path("/dev/log").exists() else ("127.0.0.1", 514)
        else:
            default = _parse_syslog_address(address)
        if isinstance(default, str) and not hasattr(socket, "AF_UNIX"):
            raise SinkError(
                f"syslog unix-socket sink {address!r} is not supported on this platform; "
                "use a host:port address instead"
            )
        try:
            self._handler = logging.handlers.SysLogHandler(address=default)
        except (OSError, ValueError, AttributeError) as exc:
            raise SinkError(f"could not open syslog sink {address!r}: {exc}") from exc
        self._logger = logging.getLogger("autoops.watch")
        self._logger.addHandler(self._handler)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

    def write_event(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, sort_keys=True, separators=(",", ":"))
        try:
            self._logger.info(line)
        except (OSError, ValueError) as exc:
            raise SinkError(f"could not write audit event to syslog: {exc}") from exc

    def close(self) -> None:
        self._logger.removeHandler(self._handler)
        self._handler.close()


def _parse_syslog_address(address: str) -> str | tuple[str, int]:
    """Parse ``/path`` or ``host:port`` syslog addresses."""
    if not address:
        raise SinkError("syslog sink address must not be empty")
    if address.startswith("/"):
        return address
    host, _, port_text = address.rpartition(":")
    if not host or not port_text.isdigit():
        raise SinkError(f"invalid syslog address: {address!r}; expected /path or host:port")
    port = int(port_text)
    if not 1 <= port <= 65535:
        raise SinkError(f"syslog port out of range: {address!r}")
    return host, port


class HttpSink(Sink):
    """POST NDJSON audit events to an HTTP(S) endpoint.

    Each watch iteration is delivered as one request whose body is the
    newline-delimited events collected during that iteration. Only ``http``
    and ``https`` URLs are accepted; URLs with embedded credentials are
    rejected rather than sent.
    """

    def __init__(self, url: str, timeout: float = _HTTP_TIMEOUT_SECONDS) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise SinkError(f"http sink URL must use http or https: {url!r}")
        if not parsed.hostname:
            raise SinkError(f"http sink URL must include a host: {url!r}")
        if parsed.username or parsed.password:
            raise SinkError("http sink URL must not embed credentials")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not (0 < timeout < 300):
            raise SinkError("http sink timeout must be a positive number below 300")
        self.url = url
        self.timeout = float(timeout)

    def write_event(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
        request = urllib.request.Request(
            self.url,
            data=line.encode("utf-8"),
            headers={"Content-Type": "application/x-ndjson"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status >= 400:
                    raise SinkError(f"http sink returned status {response.status}")
        except SinkError:
            raise
        except Exception as exc:
            raise SinkError(f"could not deliver audit event to {self.url}: {exc}") from exc

    def close(self) -> None:
        pass


def parse_sink(spec: str) -> Sink:
    """Build a sink from a CLI sink spec.

    Accepted forms: ``file:<path>``, ``syslog`` or ``syslog:<address>`` where
    address is ``/path`` or ``host:port``, and ``http(s)://<url>``.
    """
    if not isinstance(spec, str) or not spec:
        raise SinkError("sink spec must be a non-empty string")
    if spec.startswith("file:"):
        target = spec[len("file:") :]
        if not target:
            raise SinkError("file sink requires a path after 'file:'")
        return FileSink(target)
    if spec == "syslog":
        return SyslogSink()
    if spec.startswith("syslog:"):
        return SyslogSink(spec[len("syslog:") :])
    if spec.startswith(("http://", "https://")):
        return HttpSink(spec)
    raise SinkError("invalid sink spec; expected 'file:<path>', 'syslog[:address]', or an http(s) URL")


def collect_audit_events(
    operations: Sequence[Operation],
    *,
    verbose: bool = False,
    timestamp: datetime | None = None,
) -> list[dict[str, Any]]:
    """Run read-only check operations and build one redacted audit event each.

    Operations run through a non-fail-fast :class:`Workflow` so one failing
    check does not suppress the remaining checks' events. Any operation that
    declares ``mutates_state`` is rejected: watch is a read-only loop.
    """
    for operation in operations:
        if operation.mutates_state:
            raise ValueError(f"watch only runs read-only checks; {operation.name!r} declares mutates_state")
    workflow = Workflow("watch", tuple(operations), fail_fast=False)
    results = workflow.run(dry_run=True, verbose=verbose)
    occurred_at = timestamp or datetime.now(timezone.utc)
    return [build_audit_event(result, timestamp=occurred_at) for result in results.results]


def run_watch(
    operations: Sequence[Operation],
    sink: Sink,
    *,
    interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
    runs: int = 0,
    verbose: bool = False,
    stderr: TextIO | None = None,
    sleep: Callable[[float], None] | None = None,
) -> int:
    """Run checks periodically, writing redacted audit events to *sink*.

    ``runs`` bounds the number of iterations (``0`` means run forever until
    interrupted). Returns 0 on a clean stop and 2 when a sink or check
    configuration error occurs. Diagnostics go to stderr.
    """
    err = stderr or sys.stderr
    if not operations:
        print("error: watch requires at least one check operation", file=err)
        return 2
    if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float)):
        print("error: interval_seconds must be a number", file=err)
        return 2
    interval = float(interval_seconds)
    if not (0 < interval < 86400 * 7):
        print("error: interval_seconds must be positive and below one week", file=err)
        return 2
    if isinstance(runs, bool) or not isinstance(runs, int) or runs < 0:
        print("error: runs must be a non-negative integer", file=err)
        return 2

    waiter = sleep or time.sleep
    iteration = 0
    try:
        while runs == 0 or iteration < runs:
            iteration += 1
            try:
                events = collect_audit_events(tuple(operations), verbose=verbose)
            except ValueError as exc:
                print(f"error: {exc}", file=err)
                return 2
            failures = 0
            for event in events:
                try:
                    sink.write_event(event)
                except SinkError as exc:
                    print(f"error: {exc}", file=err)
                    return 2
                if not event["success"]:
                    failures += 1
            print(
                f"watch: iteration {iteration}: wrote {len(events)} audit event(s)"
                + (f", {failures} check(s) failed" if failures else ""),
                file=err,
            )
            if runs != 0 and iteration >= runs:
                break
            waiter(interval)
    except KeyboardInterrupt:
        print("watch: interrupted; stopping", file=err)
    finally:
        sink.close()
    return 0
