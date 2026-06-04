import json
import httpx
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(http_client=httpx.Client(verify=False))

SYSTEM_PROMPT = """
You are an intent classifier for an enterprise support chatbot.

Classify the user message into exactly one of these categories:

1. greeting   - casual greetings, small talk (hi, hello, good morning, how are you)

2. technical  - any question, bug report, info request, or issue that requires searching a knowledge base.
               ALSO includes questions ABOUT tickets, such as:
               "how do I create a ticket?", "where can I raise a ticket?", "what is the ticket process?"
               These are informational questions, not actions.

3. ticket_op  - ONLY when the user wants to actually PERFORM a ticket action right now:
               create a new ticket, view a specific ticket, update a ticket, or close a ticket.
               Examples: "create a ticket for my network issue", "show me ticket INC001234", "close ticket INC005678"

Respond with ONLY a JSON object in this exact format:

For greeting:
{"category": "greeting"}

For technical:
{"category": "technical"}

For ticket_op:
{"category": "ticket_op", "action": "create|view|update|close", "details": "<what the user described>"}

No explanation. No extra text. Only the JSON.
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
