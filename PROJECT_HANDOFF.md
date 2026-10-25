# Project handoff for the next workspace and chat

## Goal
Match 4 Intelligent Web Information Retrieval agent for the AMD / lablab.ai
challenge. The full competition brief had not been available in earlier
sessions. The user wants website-independent behavior, clear evidence and
decision traces, accuracy first, then speed.

## Current behavior
- Windows local version with ChatGPT Plus sign-in; account credentials are
  outside the project. The AMD GPU notebook is an earlier checkpoint.
- Scrapling and HTTP retrievers; site-local link navigation and GET forms.
- Text chunks and structured table text; fact planning, extraction, quote
  grounding, semantic fallback, final per-field review, and abstention.
- Answered results include ordered per-field `citations` with the verified
  value, source URL, passage and exact/semantic support mode. The ask CLI prints
  numbered citations; suite reports preserve them under `actual.citations`.
  Abstentions do not expose citations.
- Candidate confidence >= 0.95 for all fields prompts an early final review;
  approval can stop browsing, while rejection continues navigation.
- Configurable maximum successful pages: agent_suite.json `max_pages`
  (default 4), or `run_agent_suite.py --max-pages N` (1..20).
- Bounded parallel suite cases: `--workers 2`; final review of distinct
  fields can overlap. Within a case, discovered links are browsed sequentially.
- The user reports the tests currently pass. Run offline checks after edits,
  then measure on the real-site suite when account/network access is available.

## Workflow
Read README.md, README-agent-suite.md, AGENTS.md, and agent_suite.json.
Run `feature_selfcheck.py` and `suite_selfcheck.py`. Use the report's trace,
answer accuracy, retrieval time, model time, pages visited and fetch failures.
Do not tailor rules to one test site or discard the user's expected-answer
changes. Keep code changes small, commit each logical change and push once the
GitHub remote has been connected.

## Next feature to discuss
Adaptive retrieval: use fast static Scrapling by default; when useful content
is absent, consider browser rendering and browser-observed API responses.
Compare new static and dynamic websites for accuracy, latency, and requests.
Other ideas: read PDFs; resolve contradictory evidence and freshness; improve
answer formatting; return sources and supporting passages alongside answers.

## Boundaries
The local test reports, .venv, credentials, old code snapshots and .qodo
metadata are intentionally excluded from Git. They remain in the original
Downloads folder if needed. This new workspace contains the active source and
the local HTML test fixtures.

## Citation feature verification (2026-10-25)
- `python feature_selfcheck.py`: all 18 checks passed, covering early and final
  citations, semantic passages,
  distinct field sources, redirected URLs, rejected evidence, CLI output and
  suite report serialization. No live model or website calls are used.
- `python run_agent_suite.py --dry-run` and `git diff --check` passed.
- `suite_selfcheck.py` remains blocked in this session by Windows denying its
  localhost HTTP connection (WinError 10013); rerun outside this sandbox.
- Live website and account-backed model checks have not been run for citations.
- Commit/push pending: this session cannot create `.git/index.lock` (permission
  denied). The citation changes remain in the working tree.
