# Key prompts

Three prompts shaped this project: the brief given by the candidate, the brief the
agent wrote for its research sub-agents, and the one it wrote for its reviewers.

## Prompt: the brief

**Tool:** Claude Code (model Claude Fable 5.2)

**What was asked:**

One message, written in French, given once at the start of the session. The parts
that decided the outcome, translated:

> You are my lead engineer [...]. Objective: carry out the official Backend Developer
> recruitment challenge of Juntos Somos Mais, produce a Python project of
> professional quality, pass all the tests and prepare its GitHub submission. Do not
> just present a plan. Execute every step that can be executed [...]. Prefer a
> simple, reliable and maintainable architecture over a needlessly complex solution.

> Before coding, analyse the following repositories: FastAPI, FastAPI Best
> Practices, HTTPX, Python Phonenumbers, Pytest [...]. Also look at the previous
> submission issues of the official challenge [...]. Do not copy the solutions of
> other candidates. [...] Do not import a complete template if a few simple modules
> are enough.

> Check the real number of customers loaded. The validator expects
> `totalCount = 2000` without filter. Do not hardcode this total and do not invent
> any customer if the source is incomplete.

> WARNING: some bounds have an inverted numerical order, and their
> latitude/longitude labels can create an ambiguity. Check the coordinates of the
> real data and the published rules before choosing the interpretation. Normalise
> the bounds only after justification. [...] Do not silently modify a rule to make
> the tests pass.

> Test area codes, separators, incomplete numbers and non-numeric characters. Do not
> produce fake valid numbers by arbitrarily completing data.

> IMPORTANT: the README uses the first route [`/users`], but the official
> `validate.sh` currently tests the second one [`/api/v1/users`]. Both must return
> the same contract.

> If the official script passes while business rules fail, do not consider the
> challenge finished: its validator does not cover all the requirements.

> Make sure the application does not silently serve an incomplete data set after a
> failed load. Avoid PostgreSQL, Redis, Kubernetes, microservices and any superfluous
> component.

> Describe honestly: the AI tools actually used, the delegated tasks, the important
> prompts, the mistakes proposed by the AI, the corrected decisions, the tests
> actually run, the known limits. Do not invent human corrections or personal
> reviews that did not take place.

The brief also covered the job application itself (looking for open positions, a
draft e-mail). That part is not about the code and is left out.

**What happened:**

The agent worked from this single message to the published repository. The warnings
in the brief are where most of the judgement went:

- The bounding box warning led to measuring three readings on the real data before
  any classification code existed: nobody special or normal, 4 special and 4 normal,
  or 8 special and nobody normal.
- "Do not hardcode this total" led to comparing the two files, and to the finding
  that they contain the same 1000 customers.
- "Do not produce fake valid numbers" and the request to study python-phonenumbers
  led to measuring the library on the data, and to not using it.
- "Its validator does not cover all the requirements" led to a second, independent
  check of all 2000 customers.

**Final result:** this repository.

## Prompt: research sub-agents

**Tool:** Claude Code sub-agents (model Claude Sonnet 5.5), run in parallel

**What was asked:**

Five readers received the same rules and one repository each (a sixth agent, not
described here, looked for job openings). The rules:

> Read ONLY what is needed from the GitHub repository named below, with the
> authenticated read-only CLI [...]. Do not clone the repository, do not install
> anything, do not run third-party code, do not write files. Budget: about 12 file
> reads. [...] Every fact must carry its source: file path plus heading or line
> number. If you could not confirm something in the repository, list it under
> "unverified" instead of stating it.

And, for python-phonenumbers, after giving it four behaviours already measured
locally:

> Your job is to explain WHY from the source and metadata, so that a design decision
> can cite it precisely.

**What happened:**

- The notes came back in under two minutes, each fact with its file and heading.
- The "unverified" list was the most useful part. The FastAPI reader could not
  confirm what happens when startup fails, nor the status code of a validation
  error. Both were then settled by running the real server and the tests (exit
  code 3, and 422).
- The phonenumbers reader explained the measurements from the Brazilian metadata:
  the trunk prefix rule that drops a leading zero, and the fact that "possible" only
  checks a length between 8 and 11 digits.
- Two things the readers reported about recent FastAPI releases (defaults no longer
  validated since 0.148, the `extra` setting of query models since 0.160) were
  re-read in the official release notes before being relied on.
- What the readers could not see: Starlette's test client now wants `httpx2`. That
  only appeared when the first test was run.

**Final result:** `docs/references.md`.

## Prompt: review sub-agents

**Tool:** two Claude Code sub-agents (model Claude Sonnet 5.5), run in parallel

**What was asked:**

Both received the same frame, then one lens each: the code and its tests for one,
every claim of the documentation and the packaging files for the other. The frame,
shortened:

> You are reviewing a small Python project before it is made public. [...] You did
> not write it. Your job is to find real defects, not to praise and not to restyle.
> [...] Do NOT modify, create or delete any file inside the repository. [...] Report
> only what you can support. For each finding say whether you confirmed it by
> running something, by reading, or whether it is only plausible. [...] Do not
> report the three deliberate choices listed below unless you can show their stated
> justification is factually wrong.

The three deliberate choices were listed (the reading of the boxes, phones converted
without validation, the two files concatenated), with what had already been
verified, so that the reviewers would not spend their time redoing it.

**What happened:**

- 26 findings came back, most of them confirmed by running code. The full list and
  what was done with each is in [README.md](README.md#review-by-two-other-agents).
- Asking for the level of confidence made the triage quick: the two findings marked
  "plausible" were checked before anything was changed.
- Telling the reviewers which choices were deliberate kept them on facts. One of
  them still checked the numbers behind the choices and found that the 213 rewritten
  phone numbers were wrongly explained.

**Final result:** the fixes described in [README.md](README.md#review-by-two-other-agents).
