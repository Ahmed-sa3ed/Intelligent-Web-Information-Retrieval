# Repeatable agent checks

The suite reads agent_suite.json. Edit that file to change the model, site URLs,
questions, accepted answers, retrieval backends, or number of repeats.

Run once after each agent change from PowerShell in match4-agent-local:

    .\.venv\Scripts\python.exe run_agent_suite.py

This runs three local Cedar Museum checks and fifteen real publisher website checks,
using the Scrapling retriever and the model slug in the JSON. The current model
slug (gpt-5.6-luna) came from your previous benchmark report. Run
.\.venv\Scripts\python.exe local_agent.py models and change the JSON value if
your account lists a different slug.

Check the test runner offline without using the model:

    .\.venv\Scripts\python.exe suite_selfcheck.py

Show the planned cases without any network calls:

    .\.venv\Scripts\python.exe run_agent_suite.py --dry-run

Useful options:

- --only local: run three local cases.
- --only real: run fifteen real website cases.
- --case w3c_invention: run one named case.
- --case archives_declaration_dates: test the two-date question alone.
- --backends original scrapling: compare retrievers on the same cases.
- --model MODEL_SLUG and --repeats 2: override JSON settings for one run.
- --max-pages 6: allow up to six successfully fetched pages per case.
- --workers 2: run up to two independent website cases concurrently (default 1).

Run the full suite with bounded concurrency after the current sequential run:
    
    .\.venv\Scripts\python.exe run_agent_suite.py --workers 2

Parallel workers execute separate test cases, not every link on a website.
Within each case, the agent still visits only links discovered during
navigation and processes chunks in order. Once the pages are collected, it
reviews up to two independently requested answer fields at the same time.
Workers keep their own traces and report cases in the original configuration
order. The report includes suite_wall_seconds alongside individual run times;
compare the same case and backend across runs when evaluating accuracy.
Start with two workers. A higher setting can cause service throttling and more
requests to sites; four is the enforced maximum. Auth token refresh is
serialized between threads. For fair retriever speed comparisons, run with
--workers 1 to avoid concurrent traffic changing each backend's timing. Existing runs continue using the code already
loaded in their Python process; apply this change after they finish.

The process prints PASS/FAIL and times, then exits with code 1 if a case fails.
Each run creates a timestamped JSON report in test_reports/ and updates
test_reports/latest.json. Each case record includes the question, expected
and actual answer, total and retrieval time, page count, errors, printed agent
trace, candidate confidence, and final model reply. Reports can contain
visited URLs and extracted website text; they do not store account tokens.

The first five real-site expected answers come from the project's October 24 benchmark.
Ten additional official-site answers were checked on October 25. Each new case
labels its edge case in agent_suite.json.
A website can change or block retrieval: inspect error and trace before
deciding that a failing case is an agent regression. The comparison ignores
capitalization, whitespace, and a terminal sentence period while preserving
numbers and units. Add a legitimate alternative to a case's answers array if
its wording changes. Speed wins are counted only when both backends answer
the same case correctly.

## Retrieval and evidence diagnostics

The retrievers keep the complete HTML text and all discovered links. The agent
inspects text in overlapping chunks of about 5,000 characters, moving to the
next chunk when requested facts are still missing on that page. It offers links
to the navigation model in batches of 40; choosing no link in one batch moves
on to the next. Each visited page is still kept in full for Python evidence
validation. Final review sends only relevant excerpts of long pages to the
model, and the full source is checked again after selection.

Temporary network errors and HTTP 408, 429 and 5xx statuses receive one extra
attempt. Other HTTP failures and non-HTML pages are logged and skipped; the
agent can try another link or use evidence already collected. If it must
abstain after a fetch problem, its result includes `failure_reason` and
`fetch_failures`. The trace now records candidate confidence and source checks,
model final replies, validation failures, and the fields causing abstention.
If grounded evidence is rejected, the result also includes `selection_failures`
and a `failure_reason` with the exact validation issue.

Run these local checks before another live website run:

    .\.venv\Scripts\python.exe feature_selfcheck.py
    .\.venv\Scripts\python.exe suite_selfcheck.py

The first script uses mocked pages and requests, so it requires no ChatGPT
sign-in or website access. The second script checks the suite runner.

## Question planning and paraphrased evidence

The task planner counts independently requested answers. A question asking for
one eligibility decision across several conditions has one field; a question
asking for two separate prices has two. The field count controls the output:
Python returns the single selected value or joins several selected values with
` | ` in the requested order. This is an output contract, not a list of every
noun or action mentioned in the question.

Final evidence review first requires a source passage and answer to match
literally. If both strict attempts fail because the quote or answer wording
differs, a separate model review checks whether the proposed answer follows
from the actual page passage. It must return a continuous passage from the
fetched page, and Python checks that passage again. An ambiguous or
unsupported answer is rejected. The trace reports when semantic review ran,
its explanation, and its validation result. This extra model call costs time
and depends on the review model's judgment; source matching alone cannot prove
that a paraphrase is semantically correct.

## Early answers and browsing limit

A complete set of grounded candidates with model-supplied confidence at least
0.95 per requested field triggers an immediate final evidence review. The
review checks the question and source passages before approving an answer.
If it rejects or cannot verify a field, browsing continues. Confidence alone
cannot turn a candidate into an answer. The 0.95 threshold is a default in
agent.py; changing the number there changes the default for direct calls.

The default maximum is four successfully fetched HTML pages per case. Set
"max_pages": 6 in agent_suite.json to change the suite default, or override
it for one suite run:

    .\.venv\Scripts\python.exe run_agent_suite.py --max-pages 6 --workers 2

For a standalone question:

    .\.venv\Scripts\python.exe local_agent.py ask "https://example.org" "Your question" --model MODEL_SLUG --max-pages 6

Choose an integer from 1 to 20. Failed URLs and retries do not count as
successful pages; their fetch attempts may therefore exceed max_pages.
Increasing this limit gives difficult questions more room to navigate and can
increase run time and website requests. Early review can stop sooner than the
limit when sufficient evidence is confirmed. A higher confidence score never
substitutes for the final review.
