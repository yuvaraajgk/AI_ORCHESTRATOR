import re


def validate_intent(intent: dict) -> dict:
    category = intent.get("category")
    action   = intent.get("action")
    details  = intent.get("details") or ""

    # these categories never need extra info
    if category in ("greeting", "technical", "multi_intent", "greeting_with_intent"):
        return {"complete": True}

    if category == "ticket_op":

        if action == "create":
            if not details.strip():
                return {
                    "complete": False,
                    "missing": "issue description",
                    "ask": "What issue would you like to raise a ticket for?"
                }

        elif action == "view":
            if not _has_ticket_id(details):
                return {
                    "complete": False,
                    "missing": "ticket ID",
                    "ask": "Please provide the ticket ID you'd like to view (e.g. INC001234)."
                }

        elif action == "close":
            if not _has_ticket_id(details):
                return {
                    "complete": False,
                    "missing": "ticket ID",
                    "ask": "Please provide the ticket ID you'd like to close (e.g. INC001234)."
                }

        elif action == "update":
            if not _has_ticket_id(details):
                return {
                    "complete": False,
                    "missing": "ticket ID",
                    "ask": "Please provide the ticket ID you'd like to update (e.g. INC001234)."
                }
            if not _has_update_details(details):
                return {
                    "complete": False,
                    "missing": "update description",
                    "ask": "What changes would you like to make to the ticket?"
                }

    return {"complete": True}


def _has_ticket_id(details: str) -> bool:
    # checks for INC followed by numbers e.g. INC001234
    return bool(re.search(r'INC\d+', details, re.IGNORECASE))


def _has_update_details(details: str) -> bool:
    # must have ticket ID + additional description beyond just the ID
    cleaned = re.sub(r'INC\d+', '', details, flags=re.IGNORECASE).strip()
    return len(cleaned) > 3


_AFFIRMATIVE_PHRASES = (
    "yes", "yeah", "yep", "yup", "sure", "please do", "go ahead",
    "do it", "raise it", "raise a ticket", "create it", "create one",
    "create a ticket", "ok", "okay", "correct", "affirmative", "please"
)


def is_affirmative(text: str) -> bool:
    # deterministic yes/no gate for confirmation flows (e.g. "raise a ticket
    # for this?") — no LLM call needed for a simple accept/decline
    normalized = text.strip().lower().strip(".!? ")
    return any(phrase in normalized for phrase in _AFFIRMATIVE_PHRASES)
