import os
import time
import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

client = OpenAI(
    base_url=f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/v1",
    api_key=os.getenv("CLOUDFLARE_API_TOKEN"),
    http_client=httpx.Client(verify=False)
)

MODEL = os.getenv("CLOUDFLARE_MODEL")

MAX_RETRIES = 3


def complete(messages: list, max_tokens: int) -> str:
    # guards against a provider occasionally returning an empty/None completion
    # instead of a proper error once it's under load. Retry with backoff rather
    # than crashing on the resulting None.strip().
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
            print(f"Empty completion from provider (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {wait}s...")
            time.sleep(wait)

    raise ValueError(f"Provider returned no content after {MAX_RETRIES} attempts (last: {last_content!r})")
