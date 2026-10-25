"""Run the web agent on a laptop with ChatGPT plan sign-in."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from chatgpt_plan import available_models, sign_in
from decision import ChatGPTPlanModel

PROJECT = Path(__file__).resolve().parent


def _serve_fixtures():
    handler = partial(SimpleHTTPRequestHandler, directory=str(PROJECT / "test_site"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    parser = argparse.ArgumentParser(description="Match4 agent, laptop edition")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="Continue with ChatGPT in your browser")
    sub.add_parser("models", help="List models available to this account")
    ask = sub.add_parser("ask", help="Answer a question using a website")
    ask.add_argument("url")
    ask.add_argument("question")
    ask.add_argument("--max-pages", type=int, default=4,
                     help="Maximum successfully fetched pages (1-20; default 4)")
    for name in ("ask", "smoke", "checks"):
        command = ask if name == "ask" else sub.add_parser(name)
        command.add_argument("--model", required=True, help="Model slug from the models command")
    args = parser.parse_args()

    if args.command == "login":
        sign_in()
        return
    if args.command == "models":
        for entry in available_models():
            print(f"{entry['slug']} | {entry['display_name']}")
        return

    slugs = {item["slug"] for item in available_models()}
    if args.model not in slugs:
        parser.error("Model is not in this account's available models. Run the models command.")
    model = ChatGPTPlanModel(args.model)
    if args.command == "ask":
        if not 1 <= args.max_pages <= 20:
            parser.error("--max-pages must be from 1 to 20.")
        from agent import run_agent
        print("Result:", run_agent(args.question, args.url, model, None,
                                   max_pages=args.max_pages))
        return

    server = _serve_fixtures()
    try:
        url = f"http://127.0.0.1:{server.server_port}/index.html"
        if args.command == "smoke":
            from agent import run_agent
            result = run_agent(
                "What is adult admission to Cedar Museum?", url, model, None
            )
            print("Result:", result)
            if result != {"status": "answered", "answer": "12 EUR"}:
                raise SystemExit("Smoke check failed: model output differs from checkpoint.")
        else:
            from checks import run_checks
            from generalization_checks import run_generalization_checks
            from search_checks import run_search_checks
            run_checks(url, model, None)
            run_search_checks(model, None)
            reports = run_generalization_checks(model, None)
            if not all(item["passed"] for item in reports):
                raise SystemExit("One or more generalization checks failed.")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()

