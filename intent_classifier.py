import json
import time
from llm_client import client, MODEL

SYSTEM_PROMPT = """
You are an intent classifier for an enterprise support chatbot. Output ONLY a JSON object.

Multi-intent rules:
- greeting + one other intent → {"category": "greeting_with_intent", "other": <classify the other intent normally>}
- two or more non-greeting intents → {"category": "multi_intent"}

Single intent categories:
- greeting — hi, hello, small talk, how are you
- technical — questions, bug reports, issues, or questions ABOUT tickets (e.g. "how do I raise a ticket?"). Needs a knowledge base search, not an action.
- ticket_op — actually PERFORMING a ticket action now: create, view, update, or close. Format: {"category": "ticket_op", "action": "create|view|update|close", "details": "..."}
"""


MAX_RETRIES = 3


def classify_intent(message: str) -> dict:
    last_error = None

    for attempt in range(MAX_RETRIES):
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=200,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message}
            ]
        )
        print(f"Prompt Tokens: {response.usage.prompt_tokens}")
        content = response.choices[0].message.content
        raw = content.strip() if content else ""
        print(f"Classifier raw response: {raw!r} (finish_reason={response.choices[0].finish_reason})")

        start = raw.find("{")
        end = raw.rfind("}") + 1

        if start != -1 and end != 0:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError as e:
                last_error = e
        else:
            last_error = ValueError(f"No JSON found in classifier response: {raw!r}")

        if attempt < MAX_RETRIES - 1:
            wait = 2 ** (attempt + 1)  # 2s, 4s
            print(f"Classifier returned malformed/truncated JSON (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {wait}s...")
            time.sleep(wait)

    raise ValueError(f"Classifier failed to return valid JSON after {MAX_RETRIES} attempts: {last_error}")
