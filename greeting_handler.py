import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

client = OpenAI(
    base_url="https://ncpdev-tmp.olamagri.com/ollama/v1",
    api_key="ollama",
    http_client=httpx.Client(verify=False)
)

SYSTEM_PROMPT = "You are a friendly IT support assistant for an enterprise. Respond to greetings warmly and briefly. 1-2 sentences max."


def generate_greeting_response(message: str, history: list) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += history
    messages.append({"role": "user", "content": message})

    response = client.chat.completions.create(
        model="llama3.1:8b",
        max_tokens=100,
        messages=messages
    )
    return response.choices[0].message.content.strip()
