import os
import json
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


# ── History functions ──────────────────────────────────────────────────────────

def load_history(conversation_id: str, limit: int = None) -> list:
    raw = redis_client.get(f"session:{conversation_id}")
    history = json.loads(raw) if raw else []
    return history[-limit:] if limit else history


def save_history(conversation_id: str, history: list):
    redis_client.set(f"session:{conversation_id}", json.dumps(history))


def append_to_history(conversation_id: str, role: str, content: str):
    history = load_history(conversation_id)
    history.append({"role": role, "content": content})
    save_history(conversation_id, history)


# ── Pending state functions ────────────────────────────────────────────────────

# a stale pending clarification (e.g. "what's the ticket ID?") shouldn't be able
# to hijack a later, unrelated message days after the user abandoned the flow
PENDING_TTL_SECONDS = 300


def get_pending(conversation_id: str) -> dict | None:
    raw = redis_client.get(f"pending:{conversation_id}")
    return json.loads(raw) if raw else None


def set_pending(conversation_id: str, intent: dict):
    redis_client.set(f"pending:{conversation_id}", json.dumps(intent), ex=PENDING_TTL_SECONDS)


def clear_pending(conversation_id: str):
    redis_client.delete(f"pending:{conversation_id}")
