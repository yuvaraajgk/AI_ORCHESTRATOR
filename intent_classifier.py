import json
import httpx
from groq import Groq
from dotenv import load_dotenv

load_dotenv(override=True)

client = Groq(http_client=httpx.Client(verify=False))

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


def classify_intent(message: str) -> dict:
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=200,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message}
        ]
    )
    print(f"Prompt Tokens: {response.usage.prompt_tokens}")
    raw = response.choices[0].message.content.strip()
    return json.loads(raw)
