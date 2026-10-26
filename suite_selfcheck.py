"""Offline check for the suite runner. Does not access ChatGPT or public sites."""
import json
import httpx
from unittest.mock import patch

from collections import Counter
from run_agent_suite import (
    PROJECT, local_fixture_server, matches_expected, read_suite, run_case, summarize,
)


class FakeModel:
    def __init__(self):
        self.calls = 0

    def generate(self, messages):
        self.calls += 1
        request = json.loads(messages[-1]["content"])
        if "request_to_analyze" in request:
            return json.dumps({"required_fields": ["adult_admission"]})
        if "page" in request:
            return json.dumps({"adult_admission": {
                "value": "12 EUR",
                "quote": "Adult admission: 12 EUR.",
                "confidence": 0.93,
                "reason": "The admission price is directly stated.",
            }})
        assert request["candidate_reviews"][0]["confidence"] == 0.93
        assert request["candidate_reviews"][0]["grounded"]
        return json.dumps({
            "page_index": 0,
            "quote": "Adult admission: 12 EUR.",
            "answer": "12 EUR",
            "reason": "This is the adult price stated on the page.",
        })


config, report_dir = read_suite(PROJECT / "agent_suite.json")
assert len(config["cases"]) == 33
assert report_dir == (PROJECT / "test_reports").resolve()
assert matches_expected({"status": "answered", "answers": ["12 EUR"]},
                        {"status": "answered", "answer": " 12   eur. "})
assert not matches_expected({"status": "answered", "answers": ["12 EUR"]},
                            {"status": "answered", "answer": "12 USD"})
assert matches_expected({"status": "abstained", "answers": []},
                        {"status": "abstained", "answer": ""})
assert not matches_expected({"status": "abstained", "answers": []},
                            {"status": "answered", "answer": ""})

case = {
    "id": "offline_runner_check",
    "group": "local",
    "fixture_path": "injection.html",
    "question": "What is adult admission to Cedar Museum?",
    "expected": {"status": "answered", "answers": ["12 EUR"]},
}
model = FakeModel()
with local_fixture_server(True) as base:
    original_get = httpx.get
    def local_get(url, **kwargs):
        return original_get(url, trust_env=False, **kwargs)
    def local_fetch(url):
        from types import SimpleNamespace
        result = local_get(url, follow_redirects=True, timeout=10)
        return SimpleNamespace(url=str(result.url), status=result.status_code,
                               headers=result.headers, encoding=result.encoding,
                               body=result.content)
    with patch("retrieval.fetch_scrapling_response", side_effect=local_fetch):
        row = run_case(case, "original", model, base, 1)
assert row["passed"], (row["error"], row["trace"])
assert row["pages_fetched"] == 1 and row["fetch_attempts"] == 1
assert model.calls == 3
assert "Final model explanation" in row["trace"]
assert row["decisions"][0]["candidate_reviews"][0]["confidence"] == 0.93
summary = summarize([row], ["original"])
assert summary["backends"]["original"]["passed"] == 1
print("PASS: config, answer matching, local fetch, candidate review, report fields")


# An answered browser case only passes if the browser path was actually tried.
with local_fixture_server(True) as browser_base, \
     patch("retrieval.fetch_scrapling_response", side_effect=local_fetch):
    static_baseline = run_case({**case, "requires_browser": True}, "original",
                               FakeModel(), browser_base, 1, static_only=True)
assert static_baseline["actual"]["status"] == "answered"
assert static_baseline["browser_attempts"] == 0 and not static_baseline["passed"]
print("PASS: browser-designated cases cannot pass via static-only retrieval")

# An HTML answer cannot satisfy the PDF or conflict feature gates by luck.
with local_fixture_server(True) as feature_base, \
     patch("retrieval.fetch_scrapling_response", side_effect=local_fetch):
    feature_row = run_case({**case, "requires_pdf": True,
                            "requires_conflict": True}, "original",
                           FakeModel(), feature_base, 1)
assert feature_row["actual"]["status"] == "answered"
assert not feature_row["pdf_exercised"] and not feature_row["conflict_exercised"]
assert not feature_row["passed"]
print("PASS: PDF and conflict cases require feature evidence beyond the answer")


from pathlib import Path
from tempfile import TemporaryDirectory
from run_agent_suite import main
from contextlib import redirect_stdout
import io
with redirect_stdout(io.StringIO()) as feature_plan:
    assert main(["--feature", "pdf", "--feature", "conflict", "--dry-run"]) == 0
planned = feature_plan.getvalue().split("Cases: ", 1)[1].splitlines()[0].split(", ")
assert len(planned) == 10 and all(name.startswith(("pdf_", "conflict_")) for name in planned)
print("PASS: feature filter selects exactly the ten new public-site cases")
with TemporaryDirectory(prefix="suite-selfcheck-", dir=PROJECT) as scratch:
    assert Path(scratch).resolve().is_relative_to(PROJECT)
    with patch("run_agent_suite.read_suite",
               return_value=(config, Path(scratch))), \
         patch("run_agent_suite.available_models",
               return_value=[{"slug": "fake-model"}]), \
         patch("run_agent_suite.ChatGPTPlanModel",
               side_effect=lambda slug: FakeModel()), \
         patch("retrieval.fetch_scrapling_response", side_effect=local_fetch):
        assert main(["--model", "fake-model", "--case", "cedar_injection",
                     "--backends", "original"]) == 0
    saved = json.loads((Path(scratch) / "latest.json").read_text(encoding="utf-8"))
    assert saved["model"] == "fake-model"
    assert saved["summary"]["backends"]["original"]["passed"] == 1
    assert len(saved["runs"]) == 1 and saved["runs"][0]["passed"]
print("PASS: single-command run writes latest and archived JSON reports")



# Regression: the model may combine two answers during the first field review.
from evidence import select_facts

pages = {
    "https://example.test/branches": {
        "url": "https://example.test/branches",
        "title": "Directory",
        "text": "Staff directory and admission fees",
    },
    "https://example.test/fees": {
        "url": "https://example.test/fees",
        "title": "Fees",
        "text": "Adult admission: 12 EUR.",
    },
    "https://example.test/staff": {
        "url": "https://example.test/staff",
        "title": "Staff",
        "text": "The museum director is Mira Nabil.",
    },
}


class CombinedReplyThenCorrect:
    def __init__(self):
        self.calls = []

    def generate(self, messages):
        request = json.loads(messages[1]["content"])
        field = request["target_field"]
        assert len(request["required_fields"]) == 2
        self.calls.append(field)
        if field == "museum_director":
            if len(messages) == 2:
                return json.dumps({
                    "page_index": [2, 1],
                    "quote": "The museum director is Mira Nabil. Adult admission: 12 EUR.",
                    "answer": "Mira Nabil | 12 EUR",
                    "reason": "Combined both pages by mistake.",
                })
            assert "page_index must be one integer" in messages[-1]["content"]
            return json.dumps({
                "page_index": 2, "quote": "The museum director is Mira Nabil.",
                "answer": "Mira Nabil", "reason": "This page identifies the director.",
            })
        return json.dumps({
            "page_index": 1, "quote": "Adult admission: 12 EUR.",
            "answer": "12 EUR", "reason": "This page lists the fee.",
        })


model = CombinedReplyThenCorrect()
facts = select_facts({
    "question": "Who is the director and what is adult admission? Return NAME | PRICE",
    "required_fields": ["museum_director", "adult_admission_price"],
    "pages": pages, "candidate_reviews": [],
}, model, None)
assert Counter(model.calls) == Counter({"museum_director": 2, "adult_admission_price": 1})
assert [facts[field]["value"] for field in ("museum_director", "adult_admission_price")] == [
    "Mira Nabil", "12 EUR",
]
print("PASS: combined first reply is rejected, retried, then both fields verified")

tickets = {
    "https://example.test/visit": {
        "url": "https://example.test/visit",
        "title": "Visit",
        "text": "Free timed-entry tickets are required for entry.",
    },
}


class CombinedTicketThenCorrect:
    def __init__(self):
        self.fields = []

    def generate(self, messages):
        field = json.loads(messages[1]["content"])["target_field"]
        self.fields.append(field)
        if field == "ticket_type" and len(messages) == 2:
            return json.dumps({
                "page_index": 0,
                "quote": "Free timed-entry tickets are required for entry.",
                "answer": "free timed-entry tickets | free",
                "reason": "Combined type and price.",
            })
        return json.dumps({
            "page_index": 0,
            "quote": "Free timed-entry tickets are required for entry.",
            "answer": "Free timed-entry tickets" if field == "ticket_type" else "Free",
            "reason": "The text directly supplies this field.",
        })


model = CombinedTicketThenCorrect()
facts = select_facts({
    "question": "What type of tickets, and what price? Return TYPE | PRICE.",
    "required_fields": ["ticket_type", "ticket_price"],
    "pages": tickets, "candidate_reviews": [],
}, model, None)
assert facts["ticket_type"]["value"] == "Free timed-entry tickets"
assert facts["ticket_price"]["value"] == "Free"
assert Counter(model.fields) == Counter({"ticket_type": 2, "ticket_price": 1})
print("PASS: combined ticket answer is retried before independent price review")


class AllFieldsEvenOnFailure:
    def __init__(self):
        self.fields = []

    def generate(self, messages):
        field = json.loads(messages[1]["content"])["target_field"]
        self.fields.append(field)
        if field == "museum_director":
            return json.dumps({
                "page_index": [2, 1], "quote": "combined",
                "answer": "Mira Nabil | 12 EUR", "reason": "Invalid combined reply.",
            })
        return json.dumps({
            "page_index": 1, "quote": "Adult admission: 12 EUR.",
            "answer": "12 EUR", "reason": "The page states the fee.",
        })


model = AllFieldsEvenOnFailure()
assert select_facts({
    "question": "Director and fee?", "required_fields": [
        "museum_director", "adult_admission_price",
    ],
    "pages": pages, "candidate_reviews": [],
}, model, None) is None
assert Counter(model.fields) == Counter({"museum_director": 2, "adult_admission_price": 1})
print("PASS: unrecoverable first field does not hide the second field's decision")


# Bounded worker mode runs independent cases concurrently without mixing traces.
from time import sleep
from threading import Lock
from contextlib import nullcontext

with TemporaryDirectory(prefix="parallel-suite-", dir=PROJECT) as scratch:
    active = 0
    peak = 0
    guard = Lock()

    def fake_agent(question, start_url, model, tokenizer, *,
                   fetch_page_fn, render_page_fn, max_pages):
        assert max_pages == 2
        global active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        print("TRACE START:", question)
        sleep(0.08)
        print("TRACE END:", question)
        with guard:
            active -= 1
        value = "Mira Nabil | 12 EUR" if "director" in question else "12 EUR"
        return {"status": "answered", "answer": value}

    with patch("run_agent_suite.read_suite",
               return_value=(config, Path(scratch))), \
         patch("run_agent_suite.available_models",
               return_value=[{"slug": "fake-model"}]), \
         patch("run_agent_suite.ChatGPTPlanModel",
               side_effect=lambda slug: FakeModel()), \
         patch("run_agent_suite.run_agent", side_effect=fake_agent), \
         patch("run_agent_suite.local_fixture_server",
               side_effect=lambda enabled: nullcontext("http://127.0.0.1:12345/")):
        assert main(["--model", "fake-model", "--case", "cedar_sibling",
                     "--case", "cedar_injection", "--backends", "original",
                     "--workers", "2", "--max-pages", "2"]) == 0
    report = json.loads((Path(scratch) / "latest.json").read_text(encoding="utf-8"))
    assert peak == 2
    assert report["workers"] == 2 and report["max_pages"] == 2
    assert [row["id"] for row in report["runs"]] == [
        "cedar_sibling", "cedar_injection",
    ]
    for row in report["runs"]:
        assert row["trace"].count("TRACE START:") == 1, row["trace"]
        assert row["trace"].count("TRACE END:") == 1, row["trace"]
        assert row["question"] in row["trace"]
        assert all(other["question"] not in row["trace"]
                   for other in report["runs"] if other is not row)
    assert report["summary"]["suite_wall_seconds"] < sum(
        row["total_seconds"] for row in report["runs"])
print("PASS: two cases overlap and traces remain separate")

# Concurrent model calls should rotate an expiring login token once.
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import chatgpt_plan

token_store = {
    "scopes": ["chatgpt.tokens.use.direct"],
    "expires_at": 0, "client_id": "test-client",
    "refresh_token": "old", "access_token": "expired",
}
refreshes = []

def fake_refresh(url, *, data, timeout):
    refreshes.append(data["refresh_token"])
    sleep(0.02)
    return SimpleNamespace(is_error=False, json=lambda: {
        "access_token": "fresh", "refresh_token": "new",
        "expires_in": 3600,
    })

with patch("chatgpt_plan._load", side_effect=lambda: token_store.copy()), \
     patch("chatgpt_plan._save", side_effect=lambda record: token_store.update(record)), \
     patch("chatgpt_plan._discovery", return_value={"token_endpoint": "https://example.test/token"}), \
     patch("chatgpt_plan.httpx.post", side_effect=fake_refresh):
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: chatgpt_plan.access_token(), range(2))) == [
            "fresh", "fresh",
        ]
assert refreshes == ["old"]
print("PASS: concurrent workers refresh the login token once")


# Field reviewers overlap while returning answers in the user's requested order.
import evidence

parallel_pages = {
    "https://example.test/fees": {
        "url": "https://example.test/fees",
        "title": "Visit",
        "text": "Director: Maya Chen. Adult admission: 14 EUR.",
    },
}
field_active = 0
field_peak = 0
field_guard = Lock()

def delayed_review(request, model, tokenizer):
    global field_active, field_peak
    with field_guard:
        field_active += 1
        field_peak = max(field_peak, field_active)
    sleep(0.06)
    with field_guard:
        field_active -= 1
    field = request["target_field"]
    if field == "director":
        return {"value": "Maya Chen", "quote": "Director: Maya Chen.",
                "source_url": "https://example.test/fees"}
    return {"value": "14 EUR", "quote": "Adult admission: 14 EUR.",
            "source_url": "https://example.test/fees"}

with patch("evidence._select_one_field", side_effect=delayed_review):
    selected = evidence.select_facts({
        "question": "Who directs the museum and what is admission?",
        "required_fields": ["director", "admission"],
        "pages": parallel_pages, "candidate_reviews": [],
    }, FakeModel(), None)
assert field_peak == 2
assert [selected[key]["value"] for key in ("director", "admission")] == [
    "Maya Chen", "14 EUR",
]
print("PASS: final field reviews overlap and preserve answer order")
