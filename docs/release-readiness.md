# Release readiness

AutoOPS uses an explicit release gate so a version in package metadata is not mistaken for a validated public release. This checklist is intended to be repeatable by maintainers and auditable by reviewers.

## Candidate selection

1. Start from a clean `main` commit whose normal CI is green.
2. Record the exact commit SHA in the release tracking issue.
3. Confirm `pyproject.toml` and the intended `vX.Y.Z` tag describe the same version.
4. Confirm `CHANGELOG.md` contains a non-empty section for that version.
5. Do not move the tag to a newer commit without repeating validation and updating the recorded candidate SHA.

## Quality gates

Before tagging, verify the candidate passes the repository's normal CI matrix, including supported Python versions and the cross-platform coverage documented in the README. The release workflow then independently validates the tagged commit by:

- checking tag/package-version parity;
- running the full test suite;
- building both wheel and source distributions;
- running `twine check` on the distributions;
- force-installing the built wheel rather than relying on the editable checkout;
- smoke-testing `autoops --version`, local preflight JSON output, and `autoops-artifact` from the installed wheel;
- extracting release notes from the matching changelog section; and
- preserving the validated artifacts before the publishing job runs.

A failed validation job means the tag is not release-ready and must not be represented as a successful portfolio release.

## Safety and documentation review

Before tagging, confirm that the release still matches AutoOPS's defensive operations boundary:

- current diagnostic commands remain local and read-only;
- any state-changing operation remains dry-run by default and requires explicit operator intent;
- configuration and manifests are treated as data, not executable instructions;
- structured logging retains secret redaction behavior;
- README examples, architecture documentation, and CLI help match the shipped behavior; and
- no secrets, credentials, generated private data, or unrelated artifacts are present in the candidate.

## Publishing

Create the release tag only at the recorded, validated candidate commit. Pushing a matching `vX.Y.Z` tag triggers `.github/workflows/release.yml`. The workflow validates the tag first and only then grants the publishing job `contents: write` permission to create the GitHub Release from the already validated artifacts and changelog notes.

After publication, verify that the GitHub Release exists, its attached distributions are present, and the release notes match `CHANGELOG.md`. Then update README/roadmap language that still calls the version a release candidate.

## Current state

The package declaring a version does **not** by itself mean that version has been publicly released. Until the corresponding GitHub Release exists and the tagged workflow succeeds, describe that version as a release candidate.