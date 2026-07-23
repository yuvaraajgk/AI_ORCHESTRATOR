import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import requests
import psycopg2
import psycopg2.extras
import redis
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

BASE = "http://127.0.0.1:8000"
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)

passed = 0
failed = 0


def check(label, condition, extra=None):
    global passed, failed
    result = "PASS" if condition else "FAIL"
    print(f"  [{result}] {label}")
    if extra:
        print(f"         {extra}")
    if condition:
        passed += 1
    else:
        failed += 1


def chat(user_id, conversation_id, message):
    return requests.post(f"{BASE}/chat", json={
        "user_id": user_id,
        "conversation_id": conversation_id,
        "message": message
    }).json()


def query(sql, params):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def clean(conversation_id):
    cur = conn.cursor()
    cur.execute("DELETE FROM tickets WHERE conversation_id = %s", (conversation_id,))
    cur.execute("DELETE FROM messages WHERE conversation_id = %s", (conversation_id,))
    cur.execute("DELETE FROM conversations WHERE conversation_id = %s", (conversation_id,))
    conn.commit()
    cur.close()
    # a reused conversation_id across test runs otherwise leaves stale Redis
    # session history in place, which technical_handler.py includes as LLM
    # context — causing a later run to reference ticket IDs/details from a
    # completely different earlier run
    redis_client.delete(f"session:{conversation_id}")
    redis_client.delete(f"pending:{conversation_id}")


def extract_ticket_id(text):
    # ticket IDs appear as **INC0000042** in every response — pull it out for follow-up lookups
    import re
    match = re.search(r'INC\d+', text, re.IGNORECASE)
    return match.group(0).upper() if match else None


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 1 — create a ticket with a full description")
print("=" * 60)
clean("tkt_t1")
r = chat("u1", "tkt_t1", "create a ticket for my monitor not turning on")
response = r.get("response", "")
ticket_id = extract_ticket_id(response)
print(f"  Response: {response[:120]}")
check("response contains a ticket ID", ticket_id is not None, f"got: {response!r}")
if ticket_id:
    rows = query("SELECT * FROM tickets WHERE ticket_id = %s", (ticket_id,))
    check("ticket row created in DB", len(rows) == 1)
    if rows:
        check("status is 'open'", rows[0]["status"] == "open", f"got: {rows[0]['status']}")
        check("kb_gap is False (user-initiated, not KB-gap)", rows[0]["kb_gap"] is False)
        check("user_id stored correctly", rows[0]["user_id"] == "u1", f"got: {rows[0]['user_id']}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 2 — create with no description → pending → resume")
print("=" * 60)
clean("tkt_t2")
r1 = chat("u1", "tkt_t2", "create a ticket")
print(f"  Turn 1 response: {r1.get('response', '')[:120]}")
check("turn 1 asks for the missing description", r1.get("status") == "incomplete", f"got status: {r1.get('status')}")

r2 = chat("u1", "tkt_t2", "my keyboard isn't typing the letter e")
print(f"  Turn 2 response: {r2.get('response', '')[:120]}")
ticket_id2 = extract_ticket_id(r2.get("response", ""))
check("turn 2 creates the ticket using the resumed description", ticket_id2 is not None, f"got: {r2.get('response')!r}")
if ticket_id2:
    rows = query("SELECT description FROM tickets WHERE ticket_id = %s", (ticket_id2,))
    check("description matches the follow-up message, not 'create a ticket'",
          len(rows) == 1 and "keyboard" in rows[0]["description"].lower(),
          f"got: {rows[0]['description'] if rows else None}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 3 — view an existing ticket by ID")
print("=" * 60)
clean("tkt_t3")
r0 = chat("u1", "tkt_t3", "create a ticket for a broken office chair")
tid3 = extract_ticket_id(r0.get("response", ""))
r = chat("u1", "tkt_t3", f"show me ticket {tid3}")
response = r.get("response", "")
print(f"  Response: {response[:150]}")
check("view response includes the ticket ID", tid3 in response)
check("view response includes status", "Status:" in response)
check("view response includes description", "office chair" in response.lower())


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 4 — view is case-insensitive on the ticket ID")
print("=" * 60)
clean("tkt_t4")
r0 = chat("u1", "tkt_t4", "create a ticket for a jammed printer")
tid4 = extract_ticket_id(r0.get("response", ""))
r = chat("u1", "tkt_t4", f"show me ticket {tid4.lower()}")
response = r.get("response", "")
print(f"  Response: {response[:150]}")
check("lowercase ticket ID still resolves to the right ticket", tid4 in response, f"got: {response!r}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 5 — view a ticket ID that doesn't exist")
print("=" * 60)
clean("tkt_t5")
r = chat("u1", "tkt_t5", "show me ticket INC9999999")
response = r.get("response", "")
print(f"  Response: {response[:150]}")
check("response says the ticket wasn't found, doesn't crash",
      "couldn't find" in response.lower() or "could not find" in response.lower())


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 6 — view with no ID → pending → resume")
print("=" * 60)
clean("tkt_t6")
r0 = chat("u1", "tkt_t6", "create a ticket for a slow laptop")
tid6 = extract_ticket_id(r0.get("response", ""))
r1 = chat("u1", "tkt_t6", "can you check on my ticket")
print(f"  Turn 1 response: {r1.get('response', '')[:120]}")
check("turn 1 asks for the ticket ID", r1.get("status") == "incomplete", f"got status: {r1.get('status')}")

r2 = chat("u1", "tkt_t6", tid6)
print(f"  Turn 2 response: {r2.get('response', '')[:150]}")
check("turn 2 resolves using the resumed ID", tid6 in r2.get("response", ""))


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 7 — update an existing ticket")
print("=" * 60)
clean("tkt_t7")
r0 = chat("u1", "tkt_t7", "create a ticket for VPN dropping every few minutes")
tid7 = extract_ticket_id(r0.get("response", ""))
r = chat("u1", "tkt_t7", f"update ticket {tid7} with tried restarting the client, still happening")
response = r.get("response", "")
print(f"  Response: {response[:120]}")
check("update response references the ticket ID", tid7 in response)

rows = query("SELECT status, description FROM tickets WHERE ticket_id = %s", (tid7,))
check("status changed to in_progress", len(rows) == 1 and rows[0]["status"] == "in_progress",
      f"got: {rows[0]['status'] if rows else None}")
check("update notes appended to description", len(rows) == 1 and "restarting" in rows[0]["description"].lower())


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 8 — close an existing ticket")
print("=" * 60)
clean("tkt_t8")
r0 = chat("u1", "tkt_t8", "create a ticket for a stuck paper jam")
tid8 = extract_ticket_id(r0.get("response", ""))
r = chat("u1", "tkt_t8", f"close ticket {tid8}")
response = r.get("response", "")
print(f"  Response: {response[:120]}")
check("close response confirms closure", tid8 in response and "closed" in response.lower())

rows = query("SELECT status FROM tickets WHERE ticket_id = %s", (tid8,))
check("status changed to closed in DB", len(rows) == 1 and rows[0]["status"] == "closed",
      f"got: {rows[0]['status'] if rows else None}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 9 — close a ticket ID that doesn't exist")
print("=" * 60)
clean("tkt_t9")
r = chat("u1", "tkt_t9", "close ticket INC9999998")
response = r.get("response", "")
print(f"  Response: {response[:150]}")
check("response says the ticket wasn't found, doesn't crash",
      "couldn't find" in response.lower() or "could not find" in response.lower())


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 10 — KB-gap ticket via the ticket-offer confirmation flow")
print("Expected: a question outside the KB offers a ticket, doesn't create")
print("one until confirmed, and the resulting ticket is tagged kb_gap=True")
print("=" * 60)
clean("tkt_t10")
r1 = chat("u1", "tkt_t10", "how do I book a conference room?")
response1 = r1.get("response", "")
print(f"  Turn 1 (should be an offer, no ticket yet): {response1[:150]}")
check("turn 1 offers to raise a ticket rather than creating one immediately",
      "?" in response1 and extract_ticket_id(response1) is None, f"got: {response1!r}")

r2 = chat("u1", "tkt_t10", "yes please")
response2 = r2.get("response", "")
tid10 = extract_ticket_id(response2)
print(f"  Turn 2 (confirmed yes): {response2[:150]}")
check("turn 2 creates the ticket only after confirmation", tid10 is not None, f"got: {response2!r}")
if tid10:
    rows = query("SELECT kb_gap, original_query FROM tickets WHERE ticket_id = %s", (tid10,))
    check("ticket is tagged kb_gap=True", len(rows) == 1 and rows[0]["kb_gap"] is True)
    check("original_query captured", len(rows) == 1 and "conference room" in (rows[0]["original_query"] or "").lower())


# ─────────────────────────────────────────────────────────────────────────────
conn.close()
print("\n" + "=" * 60)
print(f"Total: {passed + failed} | Passed: {passed} | Failed: {failed}")
print("=" * 60 + "\n")
