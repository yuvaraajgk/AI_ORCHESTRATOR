import json
import time
from llm_client import client, MODEL

SYSTEM_PROMPT = """
You are an intent classifier for an enterprise support chatbot. Output ONLY a JSON object using the exact keys shown below for the matching category — never add, rename, or invent keys.

Categories:
- greeting — hi, hello, small talk, how are you → {"category": "greeting"}
- technical — a question, problem report, symptom, or follow-up needing a knowledge-base answer (not an action). This includes questions ABOUT tickets, e.g. "how do I raise a ticket?" — asking how to do something is not the same as doing it. A message is still ONE technical intent even if it mentions several symptoms, steps already tried, or ongoing frustration — as long as it is one continuous thought about one problem. → {"category": "technical"}
- ticket_op — actually PERFORMING a ticket action now: create, view, update, or close → {"category": "ticket_op", "action": "create|view|update|close", "details": "..."}

Multi-intent applies ONLY when the message bundles genuinely separate, independent requests — ones the user could just as easily have sent as two different messages. Judge this by meaning, not by sentence structure or keyword count:
- greeting + exactly one other intent → {"category": "greeting_with_intent", "other": <the other intent, classified normally using the exact shapes above>}
- two or more distinct, independent requests (e.g. two unrelated problems, or a question plus a ticket action) → {"category": "multi_intent"}

Not multi_intent (single continuous technical follow-up, despite mentioning multiple things):
"I tried restarting and reinstalling the client but it's still not connecting, what now?" → {"category": "technical"}

Is multi_intent (two separate, independent asks bundled together):
"reset my password and also create a ticket for my broken monitor" → {"category": "multi_intent"}
"""


MAX_RETRIES = 3


def classify_intent(message: str) -> dict:
    last_error = None

    for attempt in range(MAX_RETRIES):
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=200,
            temperature=0,  # classification should be deterministic, not sampled
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
