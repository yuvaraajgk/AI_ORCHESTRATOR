from llm_client import complete

SYSTEM_PROMPT = "You are a friendly IT support assistant for an enterprise. Respond to greetings warmly and briefly. 1-2 sentences max."


def generate_greeting_response(message: str, history: list) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += history
    messages.append({"role": "user", "content": message})

    return complete(messages, max_tokens=100)
