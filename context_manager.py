from cache import load_history, append_to_history
from database import conversation_exists, create_conversation, save_message


def get_history(conversation_id: str) -> list:
    return load_history(conversation_id)


def init_conversation_if_new(conversation_id: str, user_id: str):
    if not conversation_exists(conversation_id):
        create_conversation(conversation_id, user_id)


def record_user_message(conversation_id: str, user_id: str, message: str, intent_category: str):
    init_conversation_if_new(conversation_id, user_id)
    append_to_history(conversation_id, "user", message)
    save_message(conversation_id, "user", message, intent_category)


def record_assistant_response(conversation_id: str, response: str):
    append_to_history(conversation_id, "assistant", response)
    save_message(conversation_id, "assistant", response)
