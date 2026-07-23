import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import requests
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

BASE = "http://127.0.0.1:8000"
conn = psycopg2.connect(os.getenv("DATABASE_URL"))

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
    cur.execute("DELETE FROM messages WHERE conversation_id = %s", (conversation_id,))
    cur.execute("DELETE FROM conversations WHERE conversation_id = %s", (conversation_id,))
    conn.commit()
    cur.close()


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 1 — conversation row created on first message")
print("="*60)
clean("db_conv_1")
chat("u1", "db_conv_1", "my VPN is not connecting")

rows = query("SELECT * FROM conversations WHERE conversation_id = %s", ("db_conv_1",))
check("conversation row created in DB", len(rows) == 1)
if rows:
    check("user_id stored correctly", rows[0]["user_id"] == "u1",
          f"got: {rows[0]['user_id']}")
    # .days floors the gap, so "30 days minus a few seconds of test latency"
    # legitimately reads as 29 almost always and occasionally 30 — check a
    # tolerant range instead of an exact value that depends on sub-second timing
    days_ahead = (rows[0]["expires_at"].replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
    check("expires_at is ~30 days ahead",
          29 <= days_ahead <= 30,
          f"expires_at: {rows[0]['expires_at']} ({days_ahead} days ahead)")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 2 — messages saved correctly after one turn")
print("="*60)
rows = query("SELECT * FROM messages WHERE conversation_id = %s ORDER BY created_at ASC", ("db_conv_1",))
check("2 message rows created (user + assistant)", len(rows) == 2)
if len(rows) == 2:
    check("first row is user message", rows[0]["role"] == "user")
    check("user content stored correctly", rows[0]["content"] == "my VPN is not connecting",
          f"got: {rows[0]['content']}")
    check("intent_category stored on user message", rows[0]["intent_category"] == "technical",
          f"got: {rows[0]['intent_category']}")
    check("second row is assistant reply", rows[1]["role"] == "assistant")
    check("intent_category is null on assistant row", rows[1]["intent_category"] is None)


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 3 — message count grows across turns")
print("="*60)
chat("u1", "db_conv_1", "it still doesn't work")
rows = query("SELECT * FROM messages WHERE conversation_id = %s", ("db_conv_1",))
check("4 message rows after second turn", len(rows) == 4,
      f"got: {len(rows)}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 4 — conversation not duplicated on follow-up message")
print("="*60)
rows = query("SELECT * FROM conversations WHERE conversation_id = %s", ("db_conv_1",))
check("still only 1 conversation row after 2 turns", len(rows) == 1,
      f"got: {len(rows)}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 5 — last_active_at updated on each message")
print("="*60)
before = query("SELECT last_active_at FROM conversations WHERE conversation_id = %s", ("db_conv_1",))[0]["last_active_at"]
chat("u1", "db_conv_1", "how do I reset the VPN?")
after = query("SELECT last_active_at FROM conversations WHERE conversation_id = %s", ("db_conv_1",))[0]["last_active_at"]
check("last_active_at updated after new message", after > before,
      f"before: {before} | after: {after}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 6 — GET /history/{user_id} returns conversations from DB")
print("="*60)
clean("db_conv_2")
chat("u1", "db_conv_2", "create a ticket for printer issue")
r = requests.get(f"{BASE}/history/u1").json()
conv_ids = [c["conversation_id"] for c in r.get("conversations", [])]
check("API returns conversations for user", len(r.get("conversations", [])) > 0)
check("db_conv_1 present in results", "db_conv_1" in conv_ids)
check("db_conv_2 present in results", "db_conv_2" in conv_ids)


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 7 — GET /history/{conversation_id}/messages returns messages from DB")
print("="*60)
r = requests.get(f"{BASE}/history/db_conv_1/messages").json()
msgs = r.get("messages", [])
check("messages returned for conversation", len(msgs) > 0)
check("messages in chronological order",
      all(msgs[i]["created_at"] <= msgs[i+1]["created_at"] for i in range(len(msgs)-1)),
      f"message count: {len(msgs)}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 8 — ticket_op intent_category stored correctly")
print("="*60)
clean("db_conv_3")
chat("u1", "db_conv_3", "create a ticket for network issue")
rows = query("SELECT * FROM messages WHERE conversation_id = %s AND role = 'user'", ("db_conv_3",))
check("intent_category is ticket_op for ticket request", rows[0]["intent_category"] == "ticket_op",
      f"got: {rows[0]['intent_category']}")


# ─────────────────────────────────────────────────────────────────────────────
conn.close()
print("\n" + "="*60)
print(f"Total: {passed + failed} | Passed: {passed} | Failed: {failed}")
print("="*60 + "\n")
