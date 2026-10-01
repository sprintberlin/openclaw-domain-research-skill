# Contributing to OpenClaw Domain Research Skill

Contributions from humans and agents are welcome. Issues and pull requests are both encouraged.

## Issues

Use GitHub issues to report reproducible defects:

1. Search existing issues before creating a new one:
   ```bash
   gh issue list --repo sprintberlin/openclaw-domain-research-skill --state open
   ```
2. State expected vs. actual behavior and minimal reproduction steps.
3. Never include API keys, usernames, passwords, or customer-identifiable data in issue bodies or logs.

## Pull Requests

1. Branch from `main`.
2. Keep changes focused and minimal.
3. Write or update unit tests in `tests/test_domain_research.py`.
4. Verify all tests pass:
   ```bash
   python3 -m unittest discover -s tests -p 'test_*.py'
   ```
5. Ensure no secrets are included.
6. Open a PR with `gh pr create`.

## Guidelines

- Keep dependencies zero-external: use Python standard library only.
- Preserve read-only safety: never add domain purchase, mutation, or destructive API calls.
