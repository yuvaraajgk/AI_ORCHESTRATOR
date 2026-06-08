import json

# ─── REAL REDIS SETUP (uncomment when Redis is available) ──────────────────────
#
# import os
# import redis
#
# REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
# redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
#
# ── History functions ──────────────────────────────────────────────────────────
#
# def load_history(conversation_id: str) -> list:
#     raw = redis_client.get(f"session:{conversation_id}")
#     return json.loads(raw) if raw else []
#
# def save_history(conversation_id: str, history: list):
#     redis_client.set(f"session:{conversation_id}", json.dumps(history))
#
# def append_to_history(conversation_id: str, role: str, content: str):
#     history = load_history(conversation_id)
#     history.append({"role": role, "content": content})
#     save_history(conversation_id, history)
#
# ── Pending state functions ────────────────────────────────────────────────────
#
# def get_pending(conversation_id: str) -> dict | None:
#     raw = redis_client.get(f"pending:{conversation_id}")
#     return json.loads(raw) if raw else None
#
# def set_pending(conversation_id: str, intent: dict):
#     redis_client.set(f"pending:{conversation_id}", json.dumps(intent))
#
# def clear_pending(conversation_id: str):
#     redis_client.delete(f"pending:{conversation_id}")
#
# ───────────────────────────────────────────────────────────────────────────────


# ─── IN-MEMORY MOCK ────────────────────────────────────────────────────────────

_sessions: dict = {}   # conversation_id → list of messages
_pending:  dict = {}   # conversation_id → incomplete intent waiting for follow-up


# ── History functions ──────────────────────────────────────────────────────────

def load_history(conversation_id: str) -> list:
    return list(_sessions.get(conversation_id, []))


def save_history(conversation_id: str, history: list):
    _sessions[conversation_id] = history


def append_to_history(conversation_id: str, role: str, content: str):
    if conversation_id not in _sessions:
        _sessions[conversation_id] = []
    _sessions[conversation_id].append({"role": role, "content": content})


# ── Pending state functions ────────────────────────────────────────────────────

def get_pending(conversation_id: str) -> dict | None:
    return _pending.get(conversation_id)


def set_pending(conversation_id: str, intent: dict):
    _pending[conversation_id] = intent


def clear_pending(conversation_id: str):
    _pending.pop(conversation_id, None)
