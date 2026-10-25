"""Show candidate and final-answer decisions for one website question."""
import argparse
import json

import agent
import evidence
from decision import ChatGPTPlanModel


def short(value, limit=260):
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."


def enable_decision_log():
    original_extract = evidence.extract_facts
    original_reply = evidence.generate_reply
    original_select = evidence._select_one_field

    def extract_with_log(request, model, tokenizer):
        facts = original_extract(request, model, tokenizer)
        page = request["page"]
        print("\nCANDIDATES FROM", page["url"])

        for field in request["required_fields"]:
            fact = facts.get(field)
            if fact is None:
                print(" ", field, ": none")
                continue

            errors = evidence.validate_facts(
                [field], {field: fact}, {page["url"]: page}
            )
            print(" ", field, "value:", short(fact.get("value")))
            print("   quote:", short(fact.get("quote")))
            print("   Python source check:", errors or "passed")
            print("   Candidate model confidence:", fact.get("confidence"))
            print("   Candidate model reason:", fact.get("reason", ""))

        return facts

    def reply_with_log(messages, model, tokenizer):
        reply = original_reply(messages, model, tokenizer)
        try:
            request = json.loads(messages[-1]["content"])
        except (ValueError, KeyError, TypeError):
            return reply

        if "target_field" not in request:
            return reply

        print("\nFINAL MODEL CHOICE FOR", request["target_field"])
        print("  Reply:", short(reply, 600))

        try:
            choice = json.loads(reply)
            index = choice["page_index"]
            pages = request["pages"]

            if type(index) is not int or not 0 <= index < len(pages):
                print("  Chosen page: none or invalid")
                return reply

            print("  Chosen source:", pages[index]["url"])
            quote = evidence.page_quote(
                pages[index]["text"], choice["quote"]
            )
            print("  Quote found on chosen page:", quote is not None)

            if quote is not None:
                answer = evidence.page_quote(
                    quote, choice["answer"], ignore_case=True
                )
                print("  Answer found inside quote:", answer is not None)

        except (ValueError, KeyError, TypeError):
            print("  Could not parse the proposed selection")

        return reply

    def select_with_log(request, model, tokenizer, *args, **kwargs):
        result = original_select(
            request, model, tokenizer, *args, **kwargs
        )
        print("  Python selection:", result or "rejected")
        return result

    evidence.extract_facts = extract_with_log
    evidence.generate_reply = reply_with_log
    evidence._select_one_field = select_with_log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("question")
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--retriever",
        choices=("original", "scrapling"),
        default="scrapling",
    )
    args = parser.parse_args()

    fetcher = None
    if args.retriever == "scrapling":
        from retrieval_scrapling import fetch_page as fetcher

    enable_decision_log()
    result = agent.run_agent(
        args.question,
        args.url,
        ChatGPTPlanModel(args.model),
        None,
        fetch_page_fn=fetcher,
    )
    print("\nFINAL RESULT:", result)
    print(
        "Candidates guide navigation; final selection rereads "
        "the visited pages."
    )


if __name__ == "__main__":
    main()