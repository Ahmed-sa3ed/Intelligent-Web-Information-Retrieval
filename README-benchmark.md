# Scrapling comparison

The same agent, model, question, page budget, evidence checks, tables and forms
are used for both backends. The original fetches with HTTPX and parses with
BeautifulSoup. The alternative uses Scrapling's HTTP Fetcher for requests and
Scrapling DOM methods for title, links and text; table and form parsing remain
shared so the benchmark tests the retrieval change.

From PowerShell inside `match4-agent-local` after your login works:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-scrapling.txt
.\.venv\Scripts\python.exe local_agent.py models
.\.venv\Scripts\python.exe real_sites_benchmark.py --model YOUR_MODEL_SLUG
```

Use a slug from the `models` output. One default pass makes ten agent runs
(five cases for each backend). Add `--repeats 2` for two passes and twenty
agent runs, which consumes more plan usage. The order alternates by case.
No GPU or browser installation is needed for the HTTP Fetcher experiment.

Results are written to `real-site-backend-comparison.json`. Each run includes
its answer, accuracy, total time, retrieval time, pages and error, plus trace.
Compare speed on runs where both backends answered correctly. Total time
includes model inference, website fetches and navigation; the difference
between total and retrieval time also includes local agent orchestration.
One pass is indicative; repeat if you need a stronger speed conclusion.

## Five real website checks

| Publisher | Start URL | Verified answer |
| --- | --- | --- |
| NASA | https://spaceplace.nasa.gov/moon-distance/en/ | 238,855 miles |
| W3C | https://www.w3.org/about/ | Invention of Web: 1989 |
| NPS | https://www.nps.gov/linc/planyourvisit/index.htm | Undercroft advance reservation: $1.00 |
| Library of Congress | https://www.loc.gov/visit | timed-entry tickets; free |
| USGS | https://www.usgs.gov/water-science-school/science/how-much-water-there-earth | ice/glaciers share of freshwater: 68.7% |

Expected answers were checked against publisher pages on October 24, 2026.
Sites may change content, block clients or time out. Those outcomes appear as
failures rather than fast correct runs. The original requirements remain
unchanged; Scrapling is optional and specified in requirements-scrapling.txt.
Because the agent may choose different links between runs, the experiment
measures complete agent behavior, not only parser speed.
