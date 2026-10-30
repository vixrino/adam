# Rules for the Adam backend

Permanent rules for any Claude session in this repository. They apply on top of `CONTRIBUTING.md`.
When a rule and a request conflict, say so before acting.

## Language

- **Code is English**: identifiers, module/function/class names, test names, commit subjects.
- **Comments and docstrings are French.** In this backend they are written **without accents**
  (`pre-alimentation`, `ecriture`), like the existing files: keep that.
- Log messages and API `detail` messages are French without accents too.
- Existing French identifiers (for example in the worker) stay as they are. Do not rename them as a side
  effect.
- A docstring explains **why**, not what the code already says. A module docstring states the decision
  and its cost when there is one.

## Scope and diffs

- Smallest diff that solves the request. No speculative abstraction, no option nobody asked for.
- Do not reformat or re-encode files you do not otherwise change. Keep each file's line endings (many
  are CRLF): a whole-file diff from an EOL change is a defect.
- Do not rename, move or delete files outside the request. Ask first.
- Do not add a dependency without asking. Internal packages are `exa-pie` and `exa-logger` only.

## Quality (the same gates as `CONTRIBUTING.md`)

- Black and isort, line length 100. Type hints everywhere, `mypy` clean.
- Pylint >= 9.0, coverage >= 80%, docstring coverage >= 95%, bandit clean.
- Every behaviour change comes with a test. Never delete or weaken a test to get green.
- Run `python -m pytest -q` before saying a change is done, and report the result faithfully, failures
  included.

## Architecture

- Routes live under `/api/v1`. Technical routes (`/health`, `/health/ready`, docs) stay outside it.
- Fine authorization belongs in the API and the database. `conf/pie.yaml` is only a coarse filter by
  token group; a new route zone needs a pattern there (with the `/api/v1` prefix) in the same change.
- Workers read and write through the database. A worker never calls the HTTP API.
- A worker handles one document at a time in its own `try`. A failure puts that document in `ERROR`
  with the reason in `metadata["erreur"]`, and the loop continues. Each cycle that had work logs one
  summary line.
- Business rules live once, in a service (`nota_api/services/`), called by routes and workers alike.
  Routers should only load, delegate and translate errors to HTTP codes.
- No Alembic migration and no database schema change without asking: the schema is created by
  `create_all` for now.
- Never add an info or debug route. `/health` stays minimal and public.

## Security and confidentiality

- No secret, token or real hostname in code, tests, docs or commits. `.env` is never committed.
- Documents contain IBAN and NIR numbers: **never log a field value**, or any personal data. Identifiers
  and counts only. Error responses never include a driver or exception message.
- Do not weaken the guards that refuse JWT or service-token bypass outside dev/test.
- Validate at trust boundaries (configuration, request bodies, files). Fail at startup with a clear
  message rather than per request.

## Git

- Work on a branch from `develop` (`feature/...`, `fix/...`). Commit format `type(scope): description`
  (`feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `migration`).
- Never commit, push, tag or open a merge request unless asked. Never force-push. Never skip hooks.
- When asked to commit, stage the files you changed explicitly; do not `git add -A`.

## Stubs

`scripts/stubs/` exists only to run without the internal registry. Do not install a stub in an
environment that has the real packages, and do not import from `scripts/stubs/` in application code.
