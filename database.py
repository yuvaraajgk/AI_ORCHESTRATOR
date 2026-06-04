from datetime import datetime, timedelta
from uuid import uuid4
# ─── IN-MEMORY MOCK ────────────────────────────────────────────────────────────

_conversations: dict = {}   # conversation_id → conversation record
_messages: list     = []    # flat list of all messages


def create_conversation(conversation_id: str, user_id: str):
    _conversations[conversation_id] = {
        "id": str(uuid4()),
        "conversation_id": conversation_id,
        "user_id": user_id,
        "started_at": datetime.utcnow(),
        "last_active_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=30)
    }


def conversation_exists(conversation_id: str) -> bool:
    return conversation_id in _conversations


def save_message(conversation_id: str, role: str, content: str, intent_category: str = None):

    _messages.append({
        "id": str(uuid4()),
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "intent_category": intent_category,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=30)
    })
    if conversation_id in _conversations:
        _conversations[conversation_id]["last_active_at"] = datetime.utcnow()


def get_conversations_by_user(user_id: str) -> list:

    now = datetime.utcnow()
    return [
        c for c in _conversations.values()
        if c["user_id"] == user_id and c["expires_at"] > now
    ]


def get_messages_by_conversation(conversation_id: str) -> list:
    now = datetime.utcnow()
    return [
        m for m in _messages
        if m["conversation_id"] == conversation_id and m["expires_at"] > now
    ]
