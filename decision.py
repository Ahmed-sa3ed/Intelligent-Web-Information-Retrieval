"""Adapter between the existing agent prompts and ChatGPT plan inference."""
from __future__ import annotations

from openai import OpenAI

from chatgpt_plan import access_token


class ChatGPTPlanModel:
    def __init__(self, slug):
        self.slug = slug

    def generate(self, messages):
        instructions = "\n\n".join(
            message["content"] for message in messages if message["role"] == "system"
        )
        contents = [
            {"role": message["role"], "content": message["content"]}
            for message in messages if message["role"] != "system"
        ]
        client = OpenAI(
            api_key=access_token(),
            base_url="https://api.openai.com/v1",
            max_retries=0,
            timeout=60,
        )
        output = []
        completed = False
        with client.responses.create(
            model=self.slug,
            instructions=instructions,
            input=contents,
            store=False,
            stream=True,
        ) as stream:
            for event in stream:
                if event.type == "response.output_text.delta":
                    output.append(event.delta)
                elif event.type == "response.failed":
                    error = event.response.error
                    code = getattr(error, "code", None) or "unknown_error"
                    raise RuntimeError(f"ChatGPT plan request failed: {code}")
                elif event.type == "response.incomplete":
                    raise RuntimeError("ChatGPT plan response was incomplete.")
                elif event.type == "response.completed":
                    completed = True
        if not completed:
            raise RuntimeError("ChatGPT plan response ended before completion.")
        return "".join(output).strip()


def generate_reply(messages, model, tokenizer=None):
    return model.generate(messages)

