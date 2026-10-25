# Match 4 web retrieval agent

A local question-answering agent that navigates sites, uses Scrapling or HTTP
retrieval, extracts evidence, and checks answers against page passages. It can
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
