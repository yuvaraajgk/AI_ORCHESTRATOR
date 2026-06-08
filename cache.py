import json

# IN-MEMORY MOCK 

_sessions: dict = {}   # conversation_id → list of messages
_pending:  dict = {}   # conversation_id → incomplete intent waiting for follow-up


#History functions 

def load_history(conversation_id: str) -> list:
    return list(_sessions.get(conversation_id, []))


def save_history(conversation_id: str, history: list):
    _sessions[conversation_id] = history


def append_to_history(conversation_id: str, role: str, content: str):
    if conversation_id not in _sessions:
        _sessions[conversation_id] = []
    _sessions[conversation_id].append({"role": role, "content": content})


#Pending state functions

def get_pending(conversation_id: str) -> dict | None:
    return _pending.get(conversation_id)


def set_pending(conversation_id: str, intent: dict):
    _pending[conversation_id] = intent


def clear_pending(conversation_id: str):
    _pending.pop(conversation_id, None)
