# References

What was read before and during the work, in which version, and what was kept from
it. Versions are the ones resolved on 12 November 2026 and pinned in
`requirements.txt` and `requirements-dev.txt`.

## Versions

| Package | Version | Released | Role |
|---|---|---|---|
| Python | 3.14 (image), 3.12 to 3.14 (CI) | | runtime |
| fastapi | 0.162.5 | 2026-11-11 | web framework |
| starlette | 1.10.0 | 2026-10-24 | ASGI layer under FastAPI |
| pydantic | 2.14.3 | 2026-11-05 | contract, validation, settings |
| httpx | 0.28.1 | 2024-12-06 | download of the two sources |
| uvicorn | 0.54.0 | 2026-09-25 | server |
| pytest | 9.2.0 | 2026-10-27 | tests |
| pytest-cov | 7.1.0 | 2026-03-21 | coverage |
| httpx2 | 2.16.0 | 2026-10-21 | needed by Starlette's test client only |
| ruff | 0.17.4 | 2026-11-05 | lint and format |
| python-phonenumbers | 9.0.43 | 2026-11-06 | measured, not used (see below) |

## The challenge itself

Repository `juntossomosmais/backend-challenge` at commit `e3965fb` (25 February 2026).

- `README.md` and `README.pt-BR.md`: same rules in both languages.
- `validate.sh`: copied unchanged at the root of this repository. It requests
  `/api/v1/users`, while the README documents `/users`: both paths are served. It
  greps the body for `2000` anywhere and always exits 0, so CI also checks the total
  exactly.
- The issue form: its required fields shaped the submission.
- The 2019 version of the README, for the business reason behind the bounding boxes
  (`docs/decisions.md`, section 1).
- Issue #4 (the second box is SPECIAL too) and issue #1, where a maintainer writes
  that the challenge contains other "provocations" and that questions go by e-mail.
  Nothing public settles the reading of the boxes.

## FastAPI

Read: the documentation in the repository (`docs/en/docs`), the release notes of the
last twelve months, and the guidance shipped inside the installed package
(`fastapi/.agents/skills/fastapi`).

Kept:

- **Lifespan** for the startup load. `on_event` is deprecated.
- **Query parameter models** (`Annotated[UserQuery, Query()]`, available since
  0.115) with `extra="forbid"`, so that an unknown parameter is refused.
- **Return type annotations** instead of `response_model`: validation, filtering,
  documentation and serialization come from the same type.
- **`async def`** for handlers that only read memory.
- No prefix in `include_router`: the two paths are two decorators on one handler.

Recent changes that mattered:

- 0.148 (October 2026): defaults of omitted query parameters are no longer validated.
  The defaults here (page 1, size 10) are inside their bounds.
- 0.160 (October 2026): the `extra` setting of a query model applies to every query
  parameter of the request. One model holds all four parameters.
- FastAPI now depends on `opentelemetry-api` (native tracing). This was checked on
  PyPI and in FastAPI's `pyproject.toml` before the version was pinned. Exporters are
  opt-in since 0.143 and none is configured here: nothing is sent anywhere.

## fastapi-best-practices (zhanymkanov)

A community guide, read as a checklist (state of 3 May 2026).

Applies and was followed: validation with pydantic constraints and enums, no
blocking call in async code, documented routes, ruff for lint and format.

Does not apply to a service with one resource and no database, and was not adopted:
the package-per-domain layout (the guide itself says a flat layout suits small
services), database naming and migrations, background tasks, chained dependencies.

Two deliberate differences:

- The guide recommends pydantic-settings. Five environment variables are validated by
  a plain pydantic model instead, with no extra dependency.
- The guide recommends an async test client from day one. Tests use `TestClient`
  because it runs the lifespan, which is where the data is loaded.

## HTTPX

Read: `docs/advanced/timeouts.md`, `docs/exceptions.md`, `docs/advanced/transports.md`
and the response decoding code.

Kept:

- One `AsyncClient` for both downloads, with an explicit timeout. The value applies
  to each phase (connect, read, write, pool), not to the whole download.
- `raise_for_status()` raises on anything that is not 2xx, redirects included, so
  `follow_redirects=True` is set on the client.
- `httpx.HTTPError` covers network failures and bad statuses. `httpx.InvalidURL` is
  outside that hierarchy and is caught separately.
- httpx does not strip a byte order mark, and the official CSV starts with one. The
  body is decoded with `utf-8-sig`.
- `httpx.MockTransport` replaces the network in tests. Handlers return responses or
  raise `ConnectTimeout` and `ConnectError`.
- Transport retries only cover connection errors. No retry was added: a failed load
  stops the process and the container is restarted.

A note on **httpx2**: httpx has had no stable release since December 2024. In May
2026 Pydantic started `pydantic/httpx2` as its continuation, and Starlette 1.10 runs
its test client on httpx2 and warns when only httpx is installed. The application
keeps httpx, which the brief asked for and which FastAPI still recommends. httpx2 is
a development dependency for the test client alone. Moving the application itself
to httpx2 has not been tried.

## python-phonenumbers

Read: `phonenumberutil.py` (parse, possible, valid) and the Brazilian metadata
(`data/region_BR.py`). Then measured on the official data.

Result: not used. On this data set the library rewrites 213 numbers out of 2000 and
finds 697 valid, and the README's own example is not a valid number. The rule of the
challenge is a format conversion, which a small function does without changing a
digit. Figures, reasons and a snippet to reproduce are in `docs/decisions.md`,
section 2.

## pytest

Read: parametrization, fixtures, import modes, configuration reference, changelog of
the 9.x series.

Kept:

- The native `[tool.pytest]` table of pytest 9 with `strict = true`.
- `--import-mode=importlib` and `pythonpath = ["."]`, so that `pytest` works from the
  repository root without installing anything.
- `pytest.param(..., id=...)` wherever the values alone would not say what a case is
  about, so that a failure names the case.
- Warnings are errors (`filterwarnings = ["error"]`).
