import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://ncpdev-tmp.olamagri.com/ollama/v1",
    api_key="ollama",
    http_client=httpx.Client(verify=False)
)

SYSTEM_PROMPT = """
You are a query rewriter for an enterprise support chatbot. Output ONLY the rewritten query, nothing else.

Given a conversation history and the user's latest message:
- If the message is vague or refers to something in the history (e.g. "it", "this", "still not working"), rewrite it as a specific standalone search query using context from the history.
- If the message is already clear and self-contained, return it unchanged.
"""


def contextualize(message: str, history: list) -> str:
    if not history:
        return message

    history_text = "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in history)

    response = client.chat.completions.create(
        model="llama3.1:8b",
        max_tokens=100,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"History:\n{history_text}\n\nLatest message: {message}"}
        ]
    )
    return response.choices[0].message.content.strip()
