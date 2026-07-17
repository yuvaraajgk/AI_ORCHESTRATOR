import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from intent_classifier import classify_intent
from context_manager import get_history, record_user_message, record_assistant_response
from database import get_conversations_by_user, get_messages_by_conversation
from cache import get_pending, set_pending, clear_pending
from query_validator import validate_intent, is_affirmative
from query_contextualizer import contextualize
from greeting_handler import generate_greeting_response
from technical_handler import generate_technical_response
from ticket_handler import handle_ticket_op, create_kb_gap_ticket

app = FastAPI()


class UserMessage(BaseModel):
    user_id: str
    conversation_id: str
    message: str


@app.post("/chat")
async def receive_message(payload: UserMessage):

    # load session history from Redis
    history = get_history(payload.conversation_id)

    # ── Step 1: check if there's a pending incomplete intent ──────────────────
    # if the user is answering a clarification question from the previous turn,
    # skip classification and merge the reply into the pending intent
    pending = get_pending(payload.conversation_id)

    # ── Step 1a: resolve a pending "should I raise a ticket?" confirmation ────
    # a prior technical answer couldn't be found in the KB and asked the user
    # whether to raise a ticket — this message is their yes/no reply, not a
    # new request to classify
    if pending and pending.get("category") == "ticket_offer":
        clear_pending(payload.conversation_id)
        record_user_message(payload.conversation_id, payload.user_id, payload.message, "ticket_offer")

        if is_affirmative(payload.message):
            assistant_response = create_kb_gap_ticket(pending["query"], payload.user_id, payload.conversation_id)
        else:
            assistant_response = "No problem — let me know if there's anything else I can help with."

        record_assistant_response(payload.conversation_id, assistant_response)
        return {
            "status": "received",
            "session_history": history,
            "response": assistant_response
        }

    if pending:
        # user's message is the missing detail — fill it in
        pending["details"] = payload.message
        intent = pending
        clear_pending(payload.conversation_id)

    else:
        # ── Step 2: classify the intent normally ──────────────────────────────
        intent = classify_intent(payload.message)
        intent["user_id"] = payload.user_id
        intent["conversation_id"] = payload.conversation_id

        print(f"[{payload.conversation_id}] {payload.user_id}: {payload.message} → {intent}")

        # ── Step 3: handle multi-intent ───────────────────────────────────────
        # two real separate requests — ask user to send one at a time
        if intent["category"] == "multi_intent":
            clarification = "I noticed more than one request in your message. Could you send them one at a time so I can help you better?"
            record_user_message(payload.conversation_id, payload.user_id, payload.message, intent["category"])
            record_assistant_response(payload.conversation_id, clarification)
            return {
                "status": "clarification_needed",
                "intent": intent,
                "session_history": history,
                "response": clarification
            }

        # ── Step 4: handle greeting + another intent ──────────────────────────
        # greet the user and process the real intent underneath
        if intent["category"] == "greeting_with_intent":
            other = intent["other"]
            intent = other if isinstance(other, dict) else {"category": other}
            intent["user_id"] = payload.user_id
            intent["conversation_id"] = payload.conversation_id
            intent["greeted"] = True

        # ── Step 5: validate — check if required details are present ──────────
        validation = validate_intent(intent)

        if not validation["complete"]:
            # store the incomplete intent in Redis so next message can fill it
            set_pending(payload.conversation_id, intent)
            record_user_message(payload.conversation_id, payload.user_id, payload.message, intent["category"])
            record_assistant_response(payload.conversation_id, validation["ask"])
            return {
                "status": "incomplete",
                "missing": validation["missing"],
                "session_history": history,
                "response": validation["ask"]
            }

    # ── Step 6: contextualize query for technical intents ─────────────────────
    if intent["category"] == "technical":
        query = contextualize(payload.message, history)
    else:
        query = payload.message

    # ── Step 7: save user message + process ───────────────────────────────────
    record_user_message(
        payload.conversation_id,
        payload.user_id,
        payload.message,
        intent["category"]
    )

    if intent["category"] == "greeting":
        assistant_response = generate_greeting_response(payload.message, history)
    elif intent["category"] == "technical":
        assistant_response, offer_query = generate_technical_response(
            query, history,
            greeted=intent.get("greeted", False)
        )
        if offer_query:
            # don't classify the next message — treat it as this offer's yes/no reply
            set_pending(payload.conversation_id, {"category": "ticket_offer", "query": offer_query})
    elif intent["category"] == "ticket_op":
        assistant_response = handle_ticket_op(intent)
    record_assistant_response(payload.conversation_id, assistant_response)

    return {
        "status": "received",
        "intent": intent,
        "query": query,
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


# ── Frontend ────────────────────────────────────────────────────────────────
# serves the built Angular app (frontend/) from the same origin as the API,
# so the browser needs no CORS setup. Registered last so it never shadows
# the routes above — only requests that don't match /chat or /history/* fall
# through to it. Run `npm run build` in frontend/ to (re)generate this folder.
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist", "frontend", "browser")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
