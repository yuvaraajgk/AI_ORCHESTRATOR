import os
import time
import httpx
from openai import OpenAI, RateLimitError, APIStatusError, APIConnectionError
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
RETRYABLE_ERRORS = (RateLimitError, APIStatusError, APIConnectionError)


def create_with_retry(messages: list, max_tokens: int, **kwargs):
    # the provider occasionally rejects requests outright (429, connection
    # errors) under load instead of just being slow — retry with backoff
    for attempt in range(MAX_RETRIES):
        try:
            return client.chat.completions.create(model=MODEL, max_tokens=max_tokens, messages=messages, **kwargs)
        except RETRYABLE_ERRORS as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 2 ** (attempt + 2)  # 4s, 8s
            print(f"LLM request failed ({e.__class__.__name__}: {e}), retrying in {wait}s... (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait)


def complete(messages: list, max_tokens: int) -> str:
    # separately, the provider can also return a 200 with empty/None content
    # instead of a proper error under load — retry that too
    last_content = None

    for attempt in range(MAX_RETRIES):
        response = create_with_retry(messages, max_tokens)
        content = response.choices[0].message.content
        if content and content.strip():
            return content.strip()

        last_content = content
        if attempt < MAX_RETRIES - 1:
            wait = 2 ** (attempt + 1)  # 2s, 4s
            print(f"Empty completion from provider (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {wait}s...")
            time.sleep(wait)

    raise ValueError(f"Provider returned no content after {MAX_RETRIES} attempts (last: {last_content!r})")
