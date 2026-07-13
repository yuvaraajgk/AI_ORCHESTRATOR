import os
import time
import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

client = OpenAI(
    base_url=os.getenv("CEREBRAS_BASE_URL"),
    api_key=os.getenv("CEREBRAS_API_KEY"),
    http_client=httpx.Client(verify=False)
)

MODEL = os.getenv("CEREBRAS_MODEL")

MAX_RETRIES = 3


def complete(messages: list, max_tokens: int) -> str:
    # Cerebras occasionally returns an empty/None completion instead of a proper
    # 429 once a rate or token-per-minute budget is hit mid-burst. Retry with
    # backoff rather than crashing on the resulting None.strip().
    last_content = None

    for attempt in range(MAX_RETRIES):
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=max_tokens,
            messages=messages
        )
        content = response.choices[0].message.content
        if content and content.strip():
            return content.strip()

        last_content = content
        if attempt < MAX_RETRIES - 1:
            wait = 2 ** (attempt + 1)  # 2s, 4s
            print(f"Empty completion from Cerebras (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {wait}s...")
            time.sleep(wait)

    raise ValueError(f"Cerebras returned no content after {MAX_RETRIES} attempts (last: {last_content!r})")
