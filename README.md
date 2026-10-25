# Match 4 web retrieval agent

A local question-answering agent that navigates sites, uses Scrapling or HTTP
retrieval with a browser fallback for sparse JavaScript pages, extracts evidence, and checks answers against page passages. It can
follow links, submit GET search forms, read tables and long pages, abstain when
support is missing, and log how it made each decision.

## Setup (Windows PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-scrapling.txt
.\.venv\Scripts\python.exe local_agent.py login
.\.venv\Scripts\python.exe local_agent.py models
```

The sign-in stores credentials outside this repository. See
[README-local.md](README-local.md) for model setup and
[README-agent-suite.md](README-agent-suite.md) for the test suite.

## Verify and run

```powershell
.\.venv\Scripts\python.exe feature_selfcheck.py
.\.venv\Scripts\python.exe suite_selfcheck.py
.\.venv\Scripts\python.exe run_agent_suite.py --workers 2
```

The suite configuration is in [agent_suite.json](agent_suite.json).
Use `--max-pages N` to change the browsing limit for one run. Results are
written under `test_reports/`, which is excluded from Git.

## Next work

See [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) for the project state and the
next feature discussion.

## Answer citations

`run_agent` keeps the existing `status` and `answer` fields. Answered results
also include a `citations` list in requested-field order. Each citation contains
`field`, `value`, `source_url`, `quote`, and `support_mode` (`exact` or `semantic`).
The URL comes from the fetched page, including an accepted redirect; the quote
is the actual extracted page passage checked by the final evidence review.
Semantic support means the answer was approved by the semantic reviewer and
the quote was matched against the page; it does not require the answer text to
occur literally in the quote. Citations reuse that review without extra model
calls. They do not independently prove that a source's claims are true.

The `local_agent.py ask` command prints the answer followed by numbered sources
and supporting passages. Suite JSON reports retain citations under each run's
`actual.citations`; answer comparisons still use only status and answer text.
Abstained results contain no citations, including when some candidates were
found but the final review could not verify every requested field.

## Adaptive browser rendering

Static HTTP or Scrapling retrieval runs first. When a page contains a script,
its extracted text is under 600 characters, and requested facts remain missing,
the agent tries headless Chromium once for that page. It waits up to five
seconds for the visible text to grow, then parses the browser DOM through the
same HTML evidence pipeline. Static passages and links remain available when
rendering adds content. Rendering preserves the successful-page limit;
its extra attempt and time appear in the trace and suite report.
Browser failure, no new content, or an off-origin redirect leaves the static
page available for navigation. A dense shell may not meet this conservative
trigger; a page that loads content only after a click is not covered yet.

Install the optional browser dependency and binary to activate the fallback:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

`local_agent.py ask --static-only` and `run_agent_suite.py --static-only`
provide a baseline without rendering. The suite report records
`browser_attempts` and `browser_seconds` per run; `retrieval_seconds` includes
browser time. Compare the same questions with one suite worker to reduce timing
noise. Run `python adaptive_selfcheck.py` for the offline fallback checks.
