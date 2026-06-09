import json
import httpx
from groq import Groq
from dotenv import load_dotenv

load_dotenv(override=True)

client = Groq(http_client=httpx.Client(verify=False))

SYSTEM_PROMPT = """
You are an intent classifier for an enterprise support chatbot.

First, check if the user message contains MORE THAN ONE distinct intent.

If it contains multiple intents AND one of them is a greeting, respond with:
{"category": "greeting_with_intent", "other": <classify the non-greeting intent normally>}

Examples:
- "hey, how do I create a ticket?" → {"category": "greeting_with_intent", "other": {"category": "technical"}}
- "hi, create a ticket for my VPN issue" → {"category": "greeting_with_intent", "other": {"category": "ticket_op", "action": "create", "details": "VPN issue"}}

If it contains multiple non-greeting intents, respond with:
{"category": "multi_intent"}

If it contains exactly one intent, classify it into one of these categories:

1. greeting   - casual greetings, small talk (hi, hello, good morning, how are you)

2. technical  - any question, bug report, info request, or issue that requires searching a knowledge base.
               ALSO includes questions ABOUT tickets, such as:
               "how do I create a ticket?", "where can I raise a ticket?", "what is the ticket process?"
               These are informational questions, not actions.

3. ticket_op  - ONLY when the user wants to actually PERFORM a ticket action right now:
               create a new ticket, view a specific ticket, update a ticket, or close a ticket.
               Examples: "create a ticket for my network issue", "show me ticket INC001234", "close ticket INC005678"

Respond with ONLY a JSON object. No explanation. No extra text. Only the JSON.
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
