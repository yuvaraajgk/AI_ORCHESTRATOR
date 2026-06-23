import httpx
from groq import Groq
from dotenv import load_dotenv
from rag import search

load_dotenv(override=True)

client = Groq(http_client=httpx.Client(verify=False))

SYSTEM_PROMPT = """You are a helpful IT support assistant for an enterprise.
Answer the user's question using the knowledge base excerpts provided.
Be clear and concise. If the excerpts do not contain enough information to answer, say so and suggest contacting the IT Service Desk.
Do not make up steps or information that is not in the excerpts."""


def generate_technical_response(query: str, history: list, greeted: bool = False) -> str:
    chunks = search(query)
    context = "\n\n---\n\n".join(chunks)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Knowledge base:\n{context}"},
        {"role": "assistant", "content": "Understood. I will use this information to answer the user's question."},
    ]
    messages += history
    messages.append({"role": "user", "content": query})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=400,
        messages=messages
    )

    answer = response.choices[0].message.content.strip()

    if greeted:
        answer = "Hello! " + answer

    return answer
