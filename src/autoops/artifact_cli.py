"""Command-line interface for read-only artifact health checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autoops.artifacts import ArtifactExpectation, artifact_health, assess_artifacts
from autoops.reporting import to_csv


FIELDS = (
    "path",
    "size_bytes",
    "modified_at",
    "age_seconds",
    "max_age_seconds",
    "min_size_bytes",
    "state",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoops-artifact",
        description="Assess local artifact freshness and minimum size (read-only).",
    )
    parser.add_argument("path", nargs="?", help="Regular file to inspect")
    parser.add_argument("--manifest", help="JSON manifest containing an artifacts array of path/age/size expectations")
    parser.add_argument("--max-age-seconds", type=float, help="Maximum acceptable file age in seconds (required for a single path)")
    parser.add_argument("--min-size-bytes", type=int, default=0, help="Minimum acceptable file size in bytes (default: 0)")
    parser.add_argument("--fail-on-unhealthy", action="store_true", help="Return exit code 1 when any assessed artifact is unhealthy")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON")
    output.add_argument("--csv", action="store_true", dest="as_csv", help="Emit CSV")
    return parser


def _load_manifest(path: str) -> tuple[ArtifactExpectation, ...]:
    manifest_path = Path(path).resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"artifacts"} or not isinstance(data["artifacts"], list):
        raise ValueError("manifest must contain only an 'artifacts' array")
    if not data["artifacts"]:
        raise ValueError("manifest artifacts array must not be empty")

    expectations = []
    seen_paths: set[Path] = set()
    for index, item in enumerate(data["artifacts"]):
        if not isinstance(item, dict):
            raise ValueError(f"artifacts[{index}] must be an object")
        if set(item) - {"path", "max_age_seconds", "min_size_bytes"}:
            raise ValueError(f"artifacts[{index}] contains unknown keys")
        if "path" not in item or "max_age_seconds" not in item:
            raise ValueError(f"artifacts[{index}] requires path and max_age_seconds")
        path_value = item["path"]
        max_age = item["max_age_seconds"]
        min_size = item.get("min_size_bytes", 0)
        if not isinstance(path_value, str) or not path_value:
            raise ValueError(f"artifacts[{index}].path must be a non-empty string")
        if isinstance(max_age, bool) or not isinstance(max_age, (int, float)) or max_age < 0:
            raise ValueError(f"artifacts[{index}].max_age_seconds must be non-negative")
        if isinstance(min_size, bool) or not isinstance(min_size, int) or min_size < 0:
            raise ValueError(f"artifacts[{index}].min_size_bytes must be a non-negative integer")
        artifact_path = Path(path_value)
        if not artifact_path.is_absolute():
            artifact_path = manifest_path.parent / artifact_path
        artifact_path = artifact_path.resolve()
        if artifact_path in seen_paths:
            raise ValueError(f"artifacts[{index}].path duplicates an earlier resolved path")
        seen_paths.add(artifact_path)
        expectations.append(ArtifactExpectation(str(artifact_path), float(max_age), min_size))
    return tuple(expectations)


def _batch_csv(rows: tuple[object, ...]) -> str:
    rendered = [to_csv(row.to_dict(), fields=FIELDS) for row in rows]
    if not rendered:
        return to_csv({}, fields=FIELDS)
    header, first = rendered[0].split("\r\n", 1)
    bodies = [first.rstrip("\r\n")]
    for item in rendered[1:]:
        _, body = item.split("\r\n", 1)
        bodies.append(body.rstrip("\r\n"))
    return header + "\r\n" + "\r\n".join(bodies) + "\r\n"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if bool(args.path) == bool(args.manifest):
        print("error: provide exactly one of path or --manifest")
        return 2
    if args.path and args.max_age_seconds is None:
        print("error: --max-age-seconds is required when checking a single path")
        return 2
    if args.manifest and (args.max_age_seconds is not None or args.min_size_bytes != 0):
        print("error: age and size thresholds belong inside the manifest")
        return 2

    try:
        if args.manifest:
            batch = assess_artifacts(_load_manifest(args.manifest))
            if args.as_csv:
                print(_batch_csv(batch.artifacts), end="")
            elif args.as_json:
                print(json.dumps(batch.to_dict(), sort_keys=True))
            else:
                print(f"Artifacts: {batch.total} (healthy {batch.healthy}, unhealthy {batch.unhealthy})")
                for item in batch.artifacts:
                    print(f"{item.state}: {item.path}")
            unhealthy = not batch.ok
        else:
            status = artifact_health(args.path, args.max_age_seconds, min_size_bytes=args.min_size_bytes)
            payload = status.to_dict()
            if args.as_csv:
                print(to_csv(payload, fields=FIELDS), end="")
            elif args.as_json:
                print(json.dumps(payload, sort_keys=True))
            else:
                print(f"Path: {status.path}")
                print(f"Modified: {status.modified_at}")
                print(f"Size: {status.size_bytes} bytes (minimum {status.min_size_bytes})")
                print(f"Age: {status.age_seconds:.3f}s (maximum {status.max_age_seconds:.3f}s)")
                print(f"State: {status.state}")
            unhealthy = status.state != "ok"
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 2

    return 1 if args.fail_on_unhealthy and unhealthy else 0


if __name__ == "__main__":
    raise SystemExit(main())
