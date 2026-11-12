# AI journey

This folder was written by the agent at the end of the session, from what happened
in it. "The agent" means Claude Code. Nothing here describes a human review that
did not take place.

## Summary

Benjamin Da Cunha gave one detailed brief to Claude Code and let it carry out the
whole task: read the challenge, analyse the data, settle the ambiguous rules, write
the code, the tests and the documentation, have the work reviewed, and publish. No
line of this repository was typed by hand. The brief, its constraints and the
decision to publish are his. The analysis, the code and the wording of the
documents are the agent's.

When this was written, no human had reviewed the code line by line. It is said here
because the challenge asks how AI was used, and that is how.

## Tools actually used

| Tool | Model | What it did |
|---|---|---|
| Claude Code, one terminal session | Claude Fable 5.2, then Claude Opus 5.5 | Everything in this repository. The user switched the model once, after the review described below. Commits made before the switch carry a Fable 5.2 trailer, later ones an Opus 5.5 trailer. |
| Six research sub-agents | Claude Sonnet 5.5 | Five read FastAPI, fastapi-best-practices, HTTPX, python-phonenumbers and pytest and returned sourced notes. The sixth looked for current job openings, which has nothing to do with the code. |
| Two review sub-agents | Claude Sonnet 5.5 | Reviewed the finished code and tests, and every claim of the documentation, without being allowed to modify the repository. |

No other assistant, no code completion tool.

## Tasks delegated

All of them, in this order:

1. Read the official repository: both READMEs, `validate.sh`, the issue form, the
   history of the README and the earlier issues.
2. Download the two files and measure them before writing any rule.
3. Read the reference repositories (sub-agents).
4. Write the application, then the tests.
5. Run it against the real sources, with the official validator and with a second
   implementation of the rules.
6. Write the documentation, including this folder.
7. Have it reviewed by two other agents, fix what they found.
8. Publish and watch CI.

## Mistakes and corrections before the review

What the agent first intended or wrote, and what changed it.

1. **Phones with a library.** The first plan was to use python-phonenumbers. Measured
   on the real numbers, it rewrote 213 of 2000 and found the README's own example
   invalid. The plan was dropped for a small conversion function before any phone
   code was written.
2. **Dates with pydantic's own type.** `AwareDatetime` was the first choice. A quick
   experiment showed it also accepts a bare number as a Unix timestamp, so a shifted
   CSV column could become a date. Replaced by an explicit ISO 8601 parser.
3. **Out-of-date knowledge of the libraries, three times.** The agent did not know
   that FastAPI now depends on `opentelemetry-api`, that Starlette's test client now
   wants `httpx2`, or that FastAPI changed how query models treat unknown parameters.
   The first two appeared as an unexpected line in the lock file and a failing
   import, the third in the research notes. Each was checked on PyPI or in the
   upstream release notes before a version was pinned.
4. **A test that tested the mock.** One test expected a clean error for a URL without
   scheme. It failed, because the mock transport accepts such a URL where the real
   one refuses it. The test was wrong. What it revealed was right: a bad URL should be
   refused at configuration time, and now is.
5. **A secret that could reach the logs, twice.** The error messages were written to
   leave the source URL out, since a signed URL holds its secret in the query string.
   Reading the output of the real server showed two other ways in: httpx logs every
   request URL at INFO, and its error was chained into the traceback printed at
   startup. Both were closed.
6. **An invented number.** A comment claimed the in-memory filter takes "about 0.1
   ms". Nobody had measured it. Measured: about 0.2 ms. The comment and the
   documentation were corrected.
7. **100 % coverage that proved little.** All 321 tests of the first complete run
   passed, with full coverage. That says the lines run, not that a bug would be
   caught. So 45 small bugs were injected one at a time into copies of the code, and
   44 made a test fail. The review then showed that this sample had been chosen
   where tests already existed (below).
8. **A weak assertion.** One test ended with `assert a == b or a.startswith(b)`,
   written defensively. It was replaced by a single exact check.

## Review by two other agents

Two agents read the finished work with different lenses: one the code and tests, the
other every claim of the documentation, and the packaging files that could not be
run locally. They were told which choices were deliberate, and to challenge the
facts behind them, not the choices. They could run code in a scratch directory, not
modify the repository. They returned 26 findings, 10 on the code and 16 on the
documents. None changed a business rule.

On the code:

- A record with a date such as `0001-01-01T00:00:00+05:00`, or with a coordinate too
  large for a float, crashed the startup instead of being rejected. Fixed, with
  tests.
- `json.loads` raises a plain `ValueError` for an integer of more than 4300 digits,
  and a CSV header with both `name` and `name__first` raised a `TypeError`. Both
  escaped the error contract of the loaders. Fixed.
- A CSV with a renamed column started as healthy, with `null` in that field for every
  customer. The CSV header is now checked. The same drift in the JSON file is
  documented as a limit.
- Their own sample of 30 injected bugs caught only 21. The survivors pointed at what
  no test covered: the line that keeps httpx from logging URLs, the reading of the
  environment variables, the bounds of foreign phone numbers, the sorting of the
  latitude axis. Tests were added, and the 14 mutations of the code involved are all
  caught now.
- Fractions of a second were served (`03:35:31.123000Z`). They are now dropped, as
  the contract has second resolution.
- Documented rather than changed: a repeated query parameter keeps its last value, a
  download has no overall deadline, there is no rejection threshold.
- Left as it is: pydantic reads a JSON `true` postcode as 1.

On the documents:

- They said that missing coordinates give `laborious`. The code rejects such a
  record. The documents now say what the code does.
- Several sentences described as done what had not happened yet. CI had never run,
  the Python 3.12 and 3.13 runs had not been made, and the question about the boxes
  was said to be "asked in the submission issue" before any issue existed. They were
  rewritten. The runs were made locally for the state before the review, and by CI
  for the final one (below).
- Smaller inaccuracies, all corrected: "one log line" where a traceback follows, "no
  source URL is ever logged" while httpcore logs the host at DEBUG, the 213 rewritten
  numbers attributed to a leading zero only (205 are, 8 start with 90), a
  "two-line change" that also changes tests, and 100 % coverage stated while CI
  required 95 %. CI now requires 100 %.
- The CI step meant to prove that an unreachable source stops the container would
  have hung on a regression instead of failing, and accepted any exit code. It now
  has a timeout, expects exit code 3, and also covers the case where the CSV has
  already been loaded when the JSON fails.
- The README claimed a recomputation of the 2000 customers that was not in the
  repository. It is now `tools/verify_live.py`, and CI runs it.

## Checks actually run

| Check | Result |
|---|---|
| `pytest --cov` on Python 3.14.8 (macOS) | 343 passed, 100 % of lines and branches |
| The state before the review, in a fresh clone, on Python 3.12.16 and 3.13.1 | 322 passed on each. The final state was not re-run locally: the clone was refused by a disk-space guard of the development machine, and CI runs the three versions instead. |
| `ruff check` and `ruff format --check` | clean |
| Bugs injected one at a time into copies of the code: 45 before the review, 14 after | 58 of 59 caught. The survivor changes nothing observable. |
| Real server on port 8080, official sources, official `validate.sh` | `Response body is valid.` |
| `tools/verify_live.py` against that server | all checks passed: 2000 of 2000 customers, both paths, every filter |
| Real server with an unreachable source | exit code 3, one CRITICAL line, no URL path or query string in the output |
| [First CI run on GitHub](https://github.com/searadacunha/juntos-somos-mais-backend-challenge/actions/runs/43205324257): lint and tests on 3.12, 3.13 and 3.14, image built and run against the real sources | 4 jobs of 4 green. 343 passed on each version. In the container: `validate.sh` valid, `totalCount=2000` on both paths, `tools/verify_live.py` all checks passed, exit code 3 with the CSV unreachable, and with the JSON unreachable after the CSV had loaded. |

The bug injection used throwaway scripts of the session, which are not in the
repository.

Not run: Docker on the development machine (there is none, the image is built and
run by CI only), any load test, any test on non-synthetic data.

## Known limits of this way of working

- One author. The agent wrote the code, the tests and the second implementation.
  The review by two other agents found 26 things that the author had missed, which
  says that some blind spots remain.
- The reading of the bounding boxes is a judgement call made without the owner of
  the rule. It is documented and reversible, and it may still be the wrong one.
- The session was interrupted twice by usage limits and the model was switched once
  by the user. The work continued in the same conversation.
