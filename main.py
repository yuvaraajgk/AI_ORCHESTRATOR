from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from intent_classifier import classify_intent
from context_manager import get_history, record_user_message, record_assistant_response
from database import get_conversations_by_user, get_messages_by_conversation

app = FastAPI()


class UserMessage(BaseModel):
    user_id: str
    conversation_id: str
    message: str


@app.post("/chat")
async def receive_message(payload: UserMessage):
    # load session history from Redis
    history = get_history(payload.conversation_id)
    history_length = len(history)

    # classify intent
    intent = classify_intent(payload.message)
    intent["user_id"] = payload.user_id
    intent["conversation_id"] = payload.conversation_id

    print(f"[{payload.conversation_id}] {payload.user_id}: {payload.message} → {intent}")

    # handle multi-intent early — ask user to split
    if intent["category"] == "multi_intent":
        return {
            "status": "clarification_needed",
            "intent": intent,
            "session_history": history,
            "response": "I noticed more than one request in your message. Could you send them one at a time so I can help you better?"
        }

    # save user message to Redis + SQL
    record_user_message(
        payload.conversation_id,
        payload.user_id,
        payload.message,
        intent["category"]
    )

    # placeholder — response will come from decision engine / RAG / LLM
    assistant_response = "processing..."

    # save assistant response to Redis + SQL
    record_assistant_response(payload.conversation_id, assistant_response)

    return {
        "status": "received",
        "intent": intent,
        "session_history": history,
        "response": assistant_response
    }


@app.get("/history/{user_id}")
async def get_user_conversations(user_id: str):
    conversations = get_conversations_by_user(user_id)
    if not conversations:
        raise HTTPException(status_code=404, detail="No conversations found for this user")
    return {"user_id": user_id, "conversations": conversations}


@app.get("/history/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str):
    messages = get_messages_by_conversation(conversation_id)
    if not messages:
        raise HTTPException(status_code=404, detail="No messages found for this conversation")
    return {"conversation_id": conversation_id, "messages": messages}
