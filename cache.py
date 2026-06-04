import json

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
