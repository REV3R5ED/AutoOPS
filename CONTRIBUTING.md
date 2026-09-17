# Contributing to AutoOPS

Thanks for helping improve AutoOPS. Contributions should keep the project practical, observable, testable, and safe for real IT operations.

## Development setup

AutoOPS supports Python 3.10–3.13. Create a virtual environment, install the project in editable mode with its test dependencies, and run the suite before opening a pull request:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e . pytest
pytest -q
```

When changing CLI behavior, also exercise the relevant command locally, for example:

```bash
autoops disk . --json
autoops environment --json
autoops preflight . --json
```

## Safety contract

AutoOPS is designed for systems you own or administer with authorization.

- Prefer read-only operations when they solve the problem.
- State-changing operations must use the `Operation` safety contract and remain dry-run by default.
- Never add embedded credentials, tokens, private infrastructure details, or real sensitive logs to code, fixtures, examples, or documentation.
- Do not add stealth, persistence, credential collection, exploitation, destructive automation, or unauthorized remote-control behavior.
- Keep network-facing functionality defensive, explicit, and narrowly scoped.
- Preserve auditability: failures should be clear and machine-readable behavior should remain deterministic.

Use synthetic fixtures and placeholder infrastructure data in tests and examples.

## Tests and compatibility

Every behavior change should include focused regression coverage. Keep tests deterministic and independent of external services wherever practical.

GitHub Actions runs the suite on Python 3.10–3.13 on Linux and adds Windows and macOS coverage on Python 3.12. Changes to filesystem, path, process, environment, or CLI behavior should account for those supported platforms rather than assuming a single operating system.

For reporting changes, preserve stable JSON/CSV schemas unless a documented compatibility change is intentional. For state-changing operations, tests should prove that dry-run does not execute the action and that explicit execution behaves as documented.

## Pull requests

Keep each pull request focused on one meaningful improvement. Include:

- what changed and why;
- the validation or tests performed;
- user-visible documentation updates when behavior changes;
- safety implications for operations that touch system state, files, processes, services, or networking.

Avoid filler commits, generated activity, unrelated refactors, and large dependency additions without a clear operational benefit.

## Documentation

Examples should be runnable, use safe placeholder data, and make side effects obvious. New commands or configuration keys should document expected output, failure behavior, and relevant exit codes.

## Release readiness

Before a release, the repository should pass its complete CI matrix and packaging sanity checks. Release notes should describe real user-visible changes and should not claim capabilities that are not implemented and tested.
