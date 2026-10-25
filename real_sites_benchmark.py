"""Paired five-site comparison of the same agent using two HTML retrievers.

Run after local_agent.py login and models. Every run uses the same model,
question, navigation and answer checker. Results are saved as JSON.
"""
import argparse
import io
import json
import re
import statistics
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from agent import run_agent
from chatgpt_plan import available_models
from decision import ChatGPTPlanModel
from retrieval import fetch_page as fetch_original
from retrieval_scrapling import fetch_page as fetch_scrapling


CASES = [
    {
        "name": "NASA Moon distance",
        "url": "https://spaceplace.nasa.gov/moon-distance/en/",
        "question": "What is the average distance from Earth to the Moon in miles?",
        "expected": "238,855 miles",
    },
    {
        "name": "W3C invention year",
        "url": "https://www.w3.org/about/",
        "question": "In which year did Tim Berners-Lee invent the World Wide Web?",
        "expected": "1989",
    },
    {
        "name": "NPS Undercroft fee",
        "url": "https://www.nps.gov/linc/planyourvisit/index.htm",
        "question": "What is the service fee per advance reservation for the Lincoln Memorial undercroft?",
        "expected": "$1.00",
    },
    {
        "name": "Library of Congress tickets",
        "url": "https://www.loc.gov/visit",
        "question": "What type of ticket is required to enter the Library of Congress Thomas Jefferson Building, and how much does it cost? Return TYPE | PRICE.",
        "expected": "timed-entry tickets | free",
    },
    {
        "name": "USGS freshwater table",
        "url": "https://www.usgs.gov/water-science-school/science/how-much-water-there-earth",
        "question": "According to the global water distribution table, what percentage of freshwater is in ice caps, glaciers, and permanent snow?",
        "expected": "68.7%",
    },
]


def matches_expected(case, result):
    if result.get("status") != "answered":
        return False
    answer = result.get("answer", "").strip().lower()
    if case == "NASA Moon distance":
        return re.fullmatch(r"238,?855\s*(?:miles?|mi)", answer) is not None
    if case == "W3C invention year":
        return answer == "1989"
    if case == "NPS Undercroft fee":
        return re.fullmatch(r"(?:\$\s*)?1(?:\.0{1,2})?(?:\s*(?:usd|dollars?))?", answer) is not None
    if case == "Library of Congress tickets":
        fields = answer.split("|")
        return (len(fields) == 2
                and re.search(r"timed[ -]entry tickets?", fields[0]) is not None
                and fields[1].strip() == "free")
    if case == "USGS freshwater table":
        return re.fullmatch(r"68\.7\s*%?", answer) is not None
    raise ValueError(f"Unexpected case: {case}")


def run_once(case, backend, model):
    fetch = {"original": fetch_original, "scrapling": fetch_scrapling}[backend]
    metrics = {"retrieval_seconds": 0.0, "pages": 0, "fetch_attempts": 0}

    def timed_fetch(url):
        metrics["fetch_attempts"] += 1
        started = perf_counter()
        try:
            page = fetch(url)
            metrics["pages"] += 1
            return page
        finally:
            metrics["retrieval_seconds"] += perf_counter() - started

    output = io.StringIO()
    started = perf_counter()
    try:
        with redirect_stdout(output):
            result = run_agent(case["question"], case["url"], model, None,
                               fetch_page_fn=timed_fetch)
        error = None
    except Exception as exc:
        result = {"status": "error", "answer": ""}
        error = f"{type(exc).__name__}: {exc}"
    total = perf_counter() - started
    return {
        "case": case["name"], "backend": backend, "url": case["url"],
        "question": case["question"], "expected": case["expected"],
        "actual": result, "correct": matches_expected(case["name"], result),
        "total_seconds": round(total, 3),
        "retrieval_seconds": round(metrics["retrieval_seconds"], 3),
        "other_seconds": round(max(0.0, total - metrics["retrieval_seconds"]), 3),
        "pages": metrics["pages"], "fetch_attempts": metrics["fetch_attempts"],
        "error": error, "trace": output.getvalue(),
    }


def summarize(rows, repeats):
    summary = {}
    for backend in ("original", "scrapling"):
        sample = [row for row in rows if row["backend"] == backend]
        correct = [row for row in sample if row["correct"]]
        summary[backend] = {
            "correct": len(correct), "attempted": len(sample),
            "median_total_seconds_for_correct": (
                round(statistics.median(row["total_seconds"] for row in correct), 3)
                if correct else None
            ),
            "sum_total_seconds": round(sum(row["total_seconds"] for row in sample), 3),
            "sum_retrieval_seconds": round(sum(row["retrieval_seconds"] for row in sample), 3),
        }
    both_correct = [
        (case["name"], index) for index in range(repeats) for case in CASES
        if all(any(row["case"] == case["name"] and row["repeat"] == index
                   and row["backend"] == backend and row["correct"]
                   for row in rows) for backend in ("original", "scrapling"))
    ]
    summary["paired_correct_wins"] = {backend: sum(
        next(row["total_seconds"] for row in rows
             if row["case"] == case and row["repeat"] == index
             and row["backend"] == backend)
        < next(row["total_seconds"] for row in rows
               if row["case"] == case and row["repeat"] == index
               and row["backend"] != backend)
        for case, index in both_correct
    ) for backend in ("original", "scrapling")}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Slug from local_agent.py models")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5:
        parser.error("--repeats must be between 1 and 5")
    slugs = {entry["slug"] for entry in available_models()}
    if args.model not in slugs:
        parser.error("Model is unavailable. Run local_agent.py models first.")
    model = ChatGPTPlanModel(args.model)
    rows = []
    for repeat in range(args.repeats):
        for index, case in enumerate(CASES):
            # Alternate which backend goes first to reduce order bias.
            order = ("original", "scrapling") if (index + repeat) % 2 == 0 else ("scrapling", "original")
            for backend in order:
                print(f"Running {case['name']} | {backend} | pass {repeat + 1}/{args.repeats}", flush=True)
                row = run_once(case, backend, model)
                row["repeat"] = repeat
                rows.append(row)
                print(f"  {'PASS' if row['correct'] else 'FAIL'} | {row['total_seconds']} s total | "
                      f"{row['retrieval_seconds']} s retrieval | {row['actual']}"
                      + (f" | {row['error']}" if row["error"] else ""), flush=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model, "repeats": args.repeats,
        "method": "One shared agent; HTTP retrieval implementations differ. Total includes model and navigation. Accurate means the answer matches the checked source fact.",
        "summary": summarize(rows, args.repeats), "runs": rows,
    }
    path = Path(__file__).with_name("real-site-backend-comparison.json")
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Summary:", json.dumps(report["summary"], indent=2))
    print("Full report:", path)


if __name__ == "__main__":
    main()
