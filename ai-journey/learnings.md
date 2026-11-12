# Learnings

Drawn from this session only.

## What worked well

- **Measuring before choosing.** The three ambiguous points of the challenge (the
  boxes, the phones, the merge) were each settled by a short script run on the real
  files before any production code. Each of these three decisions in
  `docs/decisions.md` comes with its numbers.
- **Warnings in the brief.** The brief did not say how to read the boxes or how to
  convert a phone. It said where the traps were and what was forbidden (hardcoding
  the total, inventing valid numbers, bending a rule to pass a test). That left the
  agent free on the solution and strict on the result.
- **Sub-agents for reading, not for deciding.** Five readers went through the
  reference repositories in parallel and came back with sourced notes and, more
  useful, a list of what they could not confirm.
- **The installed package as the source of truth.** FastAPI ships its own guidance
  for coding agents inside the package, matching the installed version. Reading it
  avoided writing FastAPI the way it was written a year ago.
- **Checks that do not share the code's assumptions.** A second implementation that
  re-reads the rules from the official README, and bugs injected on purpose, say more
  than a coverage figure.
- **Reading the real output.** The two ways a source URL could reach the logs were
  found by looking at what the server actually printed, not by a test.
- **Reviewers told what not to argue about.** Listing the deliberate choices kept the
  two review agents on facts, and asking for a confidence level per finding made the
  triage of 26 findings quick.

## What did not work

- **The agent's memory of the libraries.** Three facts about FastAPI, Starlette and
  httpx had changed since its training. None was caught by reasoning: two surfaced
  as a surprise in a lock file and a failing import, the third in the research notes.
- **Trusting a first green run.** All 321 tests of the first complete run passed,
  with full coverage. Among them, one assertion was weaker than it looked, and the
  code carried a comment quoting a duration nobody had measured. Shortly before, one
  test had failed for a reason that had nothing to do with the code: it asserted a
  behaviour of the mock.
- **Choosing one's own bugs to inject.** 44 of 45 injected bugs were caught, which
  looked reassuring. The reviewers' own 30 caught only 21, because the author had
  picked bugs where tests already existed. 21 tests were added after the review.
- **Documentation written ahead of the facts.** Before the review, the documents
  described CI runs that had not happened and an issue that did not exist yet. A
  sentence is easier to check than to write correctly from memory, so each one was
  checked against a run.
- **Looking for feedback that does not exist.** The brief asked to learn from earlier
  submissions. The two submissions made since the challenge was rewritten have no
  public reply, and nothing public settles the reading of the boxes. That question
  could only be documented and asked.
- **Building the image locally.** There is no Docker on the development machine. The
  Dockerfile was written without being run, and CI is the first place where it was.

## What to do differently

- Ask the owner of the rule about the bounding boxes before writing the code. The
  challenge gives an address for questions.
- Check the versions and the release notes of every dependency first. Here it was
  done after the first surprise.
- Write the second implementation before the code, so that it cannot borrow its
  ideas.
- Let someone else choose the bugs to inject.
- Have a person read the code before it is submitted. Agents reviewing an agent is
  better than nothing and is not the same thing.
