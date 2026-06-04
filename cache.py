import json

# ─── REAL REDIS SETUP (uncomment when Redis is available) ──────────────────────
#
# import os
# import redis
#
# REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
# redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
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
# ───────────────────────────────────────────────────────────────────────────────


# ─── IN-MEMORY MOCK ────────────────────────────────────────────────────────────

_sessions: dict = {}   # conversation_id → list of messages


def load_history(conversation_id: str) -> list:
    return _sessions.get(conversation_id, [])


def save_history(conversation_id: str, history: list):
    _sessions[conversation_id] = history


def append_to_history(conversation_id: str, role: str, content: str):
    if conversation_id not in _sessions:
        _sessions[conversation_id] = []
    _sessions[conversation_id].append({"role": role, "content": content})
