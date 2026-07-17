import os
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool
from datetime import datetime, timezone
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()

_pool = SimpleConnectionPool(1, 10, os.getenv("DATABASE_URL"))


def _get_conn():
    return _pool.getconn()


def _put_conn(conn):
    _pool.putconn(conn)


def _generate_ticket_id() -> str:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM tickets")
        count = cur.fetchone()[0]
        cur.close()
        return f"INC{str(count + 1).zfill(7)}"
    finally:
        _put_conn(conn)


def create_ticket(
    description: str,
    user_id: str,
    conversation_id: str,
    kb_gap: bool = False,
    original_query: str = None
) -> str:
    ticket_id = _generate_ticket_id()
    now = datetime.now(timezone.utc)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tickets
                (id, ticket_id, user_id, conversation_id, status, description,
                 kb_gap, original_query, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'open', %s, %s, %s, %s, %s)
        """, (
            str(uuid4()), ticket_id, user_id, conversation_id,
            description, kb_gap, original_query, now, now
        ))
        conn.commit()
        cur.close()
    finally:
        _put_conn(conn)
    return ticket_id


def get_ticket(ticket_id: str) -> dict | None:
    conn = _get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM tickets WHERE ticket_id = %s", (ticket_id.upper(),))
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None
    finally:
        _put_conn(conn)


def update_ticket(ticket_id: str, update_details: str) -> bool:
    now = datetime.now(timezone.utc)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE tickets
            SET description = description || %s, status = 'in_progress', updated_at = %s
            WHERE ticket_id = %s
        """, (f"\n\n[Update] {update_details}", now, ticket_id.upper()))
        updated = cur.rowcount > 0
        conn.commit()
        cur.close()
        return updated
    finally:
        _put_conn(conn)


def close_ticket(ticket_id: str) -> bool:
    now = datetime.now(timezone.utc)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE tickets SET status = 'closed', updated_at = %s WHERE ticket_id = %s
        """, (now, ticket_id.upper()))
        updated = cur.rowcount > 0
        conn.commit()
        cur.close()
        return updated
    finally:
        _put_conn(conn)


def create_kb_gap_ticket(query: str, user_id: str, conversation_id: str) -> str:
    ticket_id = create_ticket(
        description=query,
        user_id=user_id,
        conversation_id=conversation_id,
        kb_gap=True,
        original_query=query
    )
    return (
        f"I've raised a ticket for you — **{ticket_id}**. "
        f"Our IT team will look into it shortly. "
        f"You can reference this ticket ID for updates."
    )


def handle_ticket_op(intent: dict) -> str:
    action = intent.get("action")
    details = intent.get("details", "")
    user_id = intent.get("user_id", "")
    conversation_id = intent.get("conversation_id", "")

    if action == "create":
        ticket_id = create_ticket(details, user_id, conversation_id)
        return (
            f"I've raised a ticket for you — **{ticket_id}**. "
            f"Our IT team will look into it shortly. "
            f"You can reference this ticket ID for updates or to close it once resolved."
        )

    if action == "view":
        ticket = get_ticket(_extract_ticket_id(details))
        if not ticket:
            return f"I couldn't find a ticket matching that ID. Please check the ticket number and try again."
        created = ticket["created_at"].strftime("%d %b %Y %H:%M")
        updated = ticket["updated_at"].strftime("%d %b %Y %H:%M")
        return (
            f"**{ticket['ticket_id']}**\n"
            f"Status: {ticket['status'].capitalize()}\n"
            f"Description: {ticket['description']}\n"
            f"Raised: {created} | Last updated: {updated}"
        )

    if action == "update":
        import re
        match = re.search(r'INC\d+', details, re.IGNORECASE)
        tid = match.group(0).upper() if match else ""
        update_text = re.sub(r'INC\d+', '', details, flags=re.IGNORECASE).strip(" ,.-")
        if update_ticket(tid, update_text):
            return f"Your notes have been added to **{tid}**."
        return f"I couldn't find **{tid}**. Please check the ticket number and try again."

    if action == "close":
        tid = _extract_ticket_id(details)
        if close_ticket(tid):
            return f"**{tid}** has been closed. Let me know if there's anything else I can help with."
        return f"I couldn't find **{tid}**. Please check the ticket number and try again."

    return "I didn't understand the ticket action requested."


def _extract_ticket_id(text: str) -> str:
    import re
    match = re.search(r'INC\d+', text, re.IGNORECASE)
    return match.group(0).upper() if match else ""
