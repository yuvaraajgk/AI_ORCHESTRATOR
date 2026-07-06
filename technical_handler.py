import os
import httpx
from openai import OpenAI
from dotenv import load_dotenv
from rag import search
from ticket_handler import create_ticket

load_dotenv(override=True)

client = OpenAI(
    base_url=os.getenv("CEREBRAS_BASE_URL"),
    api_key=os.getenv("CEREBRAS_API_KEY"),
    http_client=httpx.Client(verify=False)
)

# Cosine distance: 0.0 = identical, higher = less similar.
# Tune this by observing scores on real queries via GET /kb/search.
KB_GAP_THRESHOLD = 0.5

SYSTEM_PROMPT = """You are an IT support assistant for an enterprise.
Answer the user's question directly and concisely using the provided information.
Do not reference the knowledge base or excerpts in your response.
If the information is insufficient, say you don't have details on that and advise them to contact the IT Service Desk.
Do not invent steps or information not present in the provided content."""


def generate_technical_response(
    query: str,
    history: list,
    greeted: bool = False,
    user_id: str = "",
    conversation_id: str = ""
) -> str:
    chunks, scores = search(query)

    if not chunks or scores[0] > KB_GAP_THRESHOLD:
        ticket_id = create_ticket(
            description=query,
            user_id=user_id,
            conversation_id=conversation_id,
            kb_gap=True,
            original_query=query
        )
        answer = (
            f"I don't have information on that in our knowledge base yet. "
            f"I've raised a ticket — **{ticket_id}** — for our IT team to look into it. "
            f"Once it's resolved, the answer will be added to the knowledge base so future questions like this get answered directly."
        )
        if greeted:
            answer = "Hello! " + answer
        return answer

    context = "\n\n---\n\n".join(chunks)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Knowledge base:\n{context}"},
        {"role": "assistant", "content": "Understood. I will use this information to answer the user's question."},
    ]
    messages += history
    messages.append({"role": "user", "content": query})

    response = client.chat.completions.create(
        model=os.getenv("CEREBRAS_MODEL"),
        max_tokens=400,
        messages=messages
    )

    answer = response.choices[0].message.content.strip()

    if greeted:
        answer = "Hello! " + answer

    return answer
