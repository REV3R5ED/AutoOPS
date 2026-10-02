"""Tests for read-only remote SSH checks: target parsing, command allowlist, parsers."""

import pytest

from autoops import remote
from autoops.remote import (
    REMOTE_CHECK_COMMANDS,
    RemoteCheckError,
    SshTarget,
    parse_remote_disk,
    parse_remote_environment,
    parse_remote_memory,
    parse_ssh_target,
    remote_check_operation,
    run_remote_check,
)

# --- target parsing -----------------------------------------------------------


def test_parse_simple_host() -> None:
    target = parse_ssh_target("ssh://example.com")
    assert target == SshTarget(user=None, host="example.com", port=None)
    assert target.destination() == "example.com"
    assert target.label() == "example.com"


def test_parse_user_host_port() -> None:
    target = parse_ssh_target("ssh://deploy@example.com:2222")
    assert target == SshTarget(user="deploy", host="example.com", port=2222)
    assert target.destination() == "deploy@example.com"
    assert target.label() == "deploy@example.com:2222"


def test_parse_ipv6_literal() -> None:
    target = parse_ssh_target("ssh://[2001:db8::1]:2222")
    assert target.host == "[2001:db8::1]"
    assert target.port == 2222


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "http://example.com",
        "example.com",
        "ssh://",
        "ssh://host/path",
        "ssh://host?x=1",
        "ssh://host#frag",
        "ssh://-oProxyCommand=evil",
        "ssh://-host",
        "ssh://user@-host",
        "ssh://ho st",
        "ssh://host:99999",
        "ssh://host:notaport",
        "ssh://host:0",
        "ssh://::1",
        "ssh://[::1",
        "ssh://user name@host",
        "ssh://host\x00",
        "ssh://`id`",
        "ssh://host;rm -rf /",
        "ssh://host|cat /etc/passwd",
        "ssh://$(id)",
    ],
)
def test_parse_rejects_malicious_or_malformed_targets(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_ssh_target(spec)


def test_parse_rejects_non_string() -> None:
    with pytest.raises(ValueError):
        parse_ssh_target(None)


# --- command allowlist ---------------------------------------------------------


def test_allowlist_contains_only_read_only_checks() -> None:
    assert set(REMOTE_CHECK_COMMANDS) == {"disk", "environment", "memory"}


def test_disk_command_quotes_path() -> None:
    command = REMOTE_CHECK_COMMANDS["disk"]("/var/log/my dir")
    assert command.startswith("df -kP -- ")
    assert "'/var/log/my dir'" in command
    assert ";" not in command.replace("df -kP -- ", "")


def test_disk_command_rejects_relative_or_control_paths() -> None:
    with pytest.raises(ValueError):
        REMOTE_CHECK_COMMANDS["disk"]("relative/path")
    with pytest.raises(ValueError):
        REMOTE_CHECK_COMMANDS["disk"]("/tmp/x\x00")


def test_environment_and_memory_commands_take_no_arguments() -> None:
    assert "hostname" in REMOTE_CHECK_COMMANDS["environment"]()
    assert "meminfo" in REMOTE_CHECK_COMMANDS["memory"]()


def test_run_remote_check_rejects_unknown_check() -> None:
    with pytest.raises(ValueError, match="unknown remote check"):
        run_remote_check(SshTarget(None, "example.com", None), "rm -rf /")


# --- ssh invocation ------------------------------------------------------------


class _Completed:
    def __init__(self, stdout="", stderr="", returncode=0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_ssh_argv_enforces_strict_host_key_policy(monkeypatch) -> None:
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return _Completed(stdout="ok\n")

    monkeypatch.setattr(remote.shutil, "which", lambda name: "/usr/bin/ssh")
    monkeypatch.setattr(remote.subprocess, "run", fake_run)
    out = run_remote_check(SshTarget("deploy", "example.com", 2222), "environment", timeout=5)
    assert out == "ok\n"
    argv = seen["argv"]
    assert argv[0] == "ssh"
    assert "-o" in argv
    assert "StrictHostKeyChecking=yes" in argv
    assert "BatchMode=yes" in argv
    assert "-n" in argv
    assert "-p" in argv and "2222" in argv
    assert argv[-2] == "deploy@example.com"
    assert "--" in argv  # destination separated from options


def test_ssh_identity_file_must_exist(tmp_path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        run_remote_check(
            SshTarget(None, "example.com", None),
            "environment",
            identity_file=str(tmp_path / "missing_key"),
        )


def test_ssh_identity_file_is_passed_through(monkeypatch, tmp_path) -> None:
    key = tmp_path / "id_ed25519"
    key.write_text("fake-key", encoding="utf-8")
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return _Completed(stdout="ok\n")

    monkeypatch.setattr(remote.shutil, "which", lambda name: "/usr/bin/ssh")
    monkeypatch.setattr(remote.subprocess, "run", fake_run)
    run_remote_check(SshTarget(None, "example.com", None), "memory", identity_file=str(key))
    assert "-i" in seen["argv"]
    assert str(key) in seen["argv"]


def test_remote_failure_reports_host_and_check(monkeypatch) -> None:
    def fake_run(argv, **kwargs):
        return _Completed(stderr="Host key verification failed.", returncode=255)

    monkeypatch.setattr(remote.shutil, "which", lambda name: "/usr/bin/ssh")
    monkeypatch.setattr(remote.subprocess, "run", fake_run)
    with pytest.raises(RemoteCheckError, match="example.com.*environment|Host key"):
        run_remote_check(SshTarget(None, "example.com", None), "environment")


def test_missing_ssh_binary_is_remote_error(monkeypatch) -> None:
    monkeypatch.setattr(remote.shutil, "which", lambda name: None)
    with pytest.raises(RemoteCheckError, match="ssh.*not found"):
        run_remote_check(SshTarget(None, "example.com", None), "environment")


def test_invalid_timeout_rejected() -> None:
    with pytest.raises(ValueError):
        run_remote_check(SshTarget(None, "example.com", None), "environment", timeout=0)
    with pytest.raises(ValueError):
        run_remote_check(SshTarget(None, "example.com", None), "environment", timeout=301)


# --- output parsers -------------------------------------------------------------


def test_parse_remote_disk() -> None:
    output = (
        "Filesystem     1024-blocks    Used Available Capacity Mounted on\n"
        "/dev/sda1        20971520 5242880  15728640      25% /\n"
    )
    parsed = parse_remote_disk(output, "/")
    assert parsed["total_bytes"] == 20971520 * 1024
    assert parsed["used_bytes"] == 5242880 * 1024
    assert parsed["free_bytes"] == 15728640 * 1024
    assert parsed["used_percent"] == 25.0
    assert parsed["path"] == "/"


def test_parse_remote_disk_rejects_garbage() -> None:
    with pytest.raises(RemoteCheckError):
        parse_remote_disk("nothing useful\n", "/")
    with pytest.raises(RemoteCheckError):
        parse_remote_disk("Filesystem\n/dev/sda1 not numbers here\n", "/")


def test_parse_remote_environment() -> None:
    output = "web-01\nLinux\n6.8.0\nx86_64\n8\n"
    parsed = parse_remote_environment(output)
    assert parsed == {
        "hostname": "web-01",
        "platform": "Linux",
        "platform_release": "6.8.0",
        "architecture": "x86_64",
        "cpu_count": 8,
    }


def test_parse_remote_environment_unknown_cpu() -> None:
    parsed = parse_remote_environment("web-01\nLinux\n6.8.0\nx86_64\nunknown\n")
    assert parsed["cpu_count"] is None


def test_parse_remote_environment_rejects_short_output() -> None:
    with pytest.raises(RemoteCheckError):
        parse_remote_environment("web-01\nLinux\n")


def test_parse_remote_memory() -> None:
    output = "MemTotal:       16384000 kB\nMemAvailable:    4096000 kB\n"
    parsed = parse_remote_memory(output)
    assert parsed["total_bytes"] == 16384000 * 1024
    assert parsed["available_bytes"] == 4096000 * 1024
    assert parsed["used_percent"] == 75.0


def test_parse_remote_memory_rejects_incomplete() -> None:
    with pytest.raises(RemoteCheckError):
        parse_remote_memory("MemTotal: 100 kB\n")


# --- Operation contract -----------------------------------------------------------


def test_remote_check_operation_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        remote,
        "run_remote_check",
        lambda target, check, *args, **kwargs: (
            "Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/sda1 100 25 75 25% /\n"
        ),
    )
    operation = remote_check_operation(SshTarget(None, "example.com", None), "disk", "/")
    assert operation.mutates_state is False
    assert "example.com" in operation.name
    result = operation.run()  # read-only: executes even under default dry-run
    assert result.success
    assert result.data["used_percent"] == 25.0


def test_remote_check_operation_rejects_unknown_check() -> None:
    with pytest.raises(ValueError, match="unknown remote check"):
        remote_check_operation(SshTarget(None, "example.com", None), "nmap")
