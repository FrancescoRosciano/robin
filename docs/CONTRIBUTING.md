# Contributing — Robin

Hackathon build. Generated sections are marked; do not hand-edit them —
update the source of truth and regenerate (`/ecc:update-docs`).

## Prerequisites

- **Docker** (the only supported dev environment). This machine runs
  ThreatLocker; host Python/wheels are blocked. The container *is* the
  environment — do not run the host Python.
- A `.env` (copy from `.env.example`; gitignored; never commit).

## Environment setup

```bash
cp .env.example .env          # fill in real values — see source of truth below
docker compose build robin    # python:3.12-slim + full stack
```

Required vars are validated at startup (fail-fast). **Source of truth:**
`src/robin/config.py` (`_REQUIRED`). Annotated template: `.env.example`.

<!-- AUTO-GENERATED: commands (from docker-compose.yml + pyproject.toml) -->
| Command | Purpose |
|---------|---------|
| `docker compose run --rm robin pytest -q` | Run the test suite (the compose default `command`) |
| `docker compose run --rm robin ruff check src tests` | Lint (ruff, line-length 100, target py311) |
| `docker compose build robin` | Rebuild image (only when `requirements*.txt` change) |
| `docker compose run --rm robin pytest --cov=robin --cov-report=term-missing` | Tests with coverage (pyproject default addopts) |

Test config (pyproject): `pythonpath=["src"]`, `testpaths=["tests"]`,
`asyncio_mode="auto"`. Server: host `:8080` → container `:8000` (see
`docs/RUNBOOK.md`).
<!-- /AUTO-GENERATED -->

## Testing

- **TDD is mandatory** (RED → GREEN → REFACTOR); ≥80% coverage on the
  testable core. Pure logic (context pack, prompt render, classifier)
  is telephony-independent — unit-test it without a phone.
- New feature / bug fix → use the `tdd-guide` agent.

## Code style

- PEP 8, type annotations on all signatures, immutable patterns
  (`@dataclass(frozen=True)`), functions <50 lines, files <800.
- `ruff` must be clean; no debug prints.

## PR / commit checklist

<!-- AUTO-GENERATED: gate (from .claude/rules + hackathon.md) -->
- [ ] Tests written first; suite green; ≥80% coverage on testable core
- [ ] `ruff check src tests` clean; no stray prints
- [ ] `code-reviewer` + `security-reviewer` run; CRITICAL/HIGH fixed
- [ ] Webhook signature verification intact (Svix; `src/robin/signature.py`)
- [ ] No secrets / real PII / `.env` / recordings staged
- [ ] Conventional commit (`feat:`/`fix:`/`refactor:`/`test:`/`docs:`/`chore:`)
- [ ] Agent does **not** `git push` (denied; the human submits)
<!-- /AUTO-GENERATED -->
