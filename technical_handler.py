from llm_client import complete
from rag import search

# Cosine distance: 0.0 = identical, higher = less similar.
# Tune this by observing scores on real queries via GET /kb/search.
KB_GAP_THRESHOLD = 0.5

SYSTEM_PROMPT = """You are an IT support assistant for an enterprise.
Answer the user's question directly and concisely using the provided information.
Do not reference the knowledge base or excerpts in your response.
Do not invent steps or information not present in the provided content.
If the provided information does not answer the question, respond with exactly: NOT_FOUND"""

TICKET_OFFER_MESSAGE = "I don't have information on that in our knowledge base. Would you like me to raise a ticket so our IT team can look into it?"


def generate_technical_response(
    query: str,
    history: list,
    greeted: bool = False
) -> tuple[str, str | None]:
    """Returns (answer, offer_query). offer_query is the original question when
    the KB couldn't answer it and the user should be asked whether to raise a
    ticket — None when a real answer was given and no offer is needed."""
    chunks, scores = search(query)

    if not chunks or scores[0] > KB_GAP_THRESHOLD:
        answer = TICKET_OFFER_MESSAGE
        if greeted:
            answer = "Hello! " + answer
        return answer, query

    context = "\n\n---\n\n".join(chunks)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Knowledge base:\n{context}"},
        {"role": "assistant", "content": "Understood. I will use this information to answer the user's question."},
    ]
    messages += history
    messages.append({"role": "user", "content": query})

    answer = complete(messages, max_tokens=400)

    if answer.strip() == "NOT_FOUND":
        answer = TICKET_OFFER_MESSAGE
        if greeted:
            answer = "Hello! " + answer
        return answer, query

    if greeted:
        answer = "Hello! " + answer

    return answer, None
