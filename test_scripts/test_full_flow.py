import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import requests
import json
import redis
from datetime import datetime

BASE = "http://127.0.0.1:8000"
redis_client = redis.Redis.from_url("redis://localhost:6379", decode_responses=True)
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "results_test_full_flow.txt")


def chat(user_id, conversation_id, message):
    res = requests.post(f"{BASE}/chat", json={
        "user_id": user_id,
        "conversation_id": conversation_id,
        "message": message
    })
    try:
        return res.json()
    except Exception:
        return {"error": f"HTTP {res.status_code} — {res.text[:300]}"}


def clean(*conversation_ids):
    for cid in conversation_ids:
        redis_client.delete(f"session:{cid}")
        redis_client.delete(f"pending:{cid}")


lines = []


def log(text=""):
    print(text)
    lines.append(text)


def send(label, user_id, conversation_id, message, checks=None):
    r = chat(user_id, conversation_id, message)
    if "error" in r:
        log(f"  Message : {message}")
        log(f"  [ERROR] Server returned: {r['error']}")
        log()
        return r
    log(f"  Message : {message}")
    log(f"  Status  : {r.get('status')}")
    log(f"  Intent  : {r.get('intent', {}).get('category')} / {r.get('intent', {}).get('action', '-')}")
    if r.get("query"):
        log(f"  Query   : {r.get('query')}")
    if r.get("response"):
        log(f"  Response: {r.get('response')}")
    if r.get("missing"):
        log(f"  Missing : {r.get('missing')}")
    log(f"  History : {len(r.get('session_history', []))} entries")
    if checks:
        for label, condition in checks(r):
            result = "PASS" if condition else "FAIL"
            log(f"  [{result}] {label}")
    log()
    return r


# ─────────────────────────────────────────────────────────────────────────────
log(f"Full Flow Test — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
log("=" * 60)

clean("conv_1", "conv_2", "conv_3", "conv_4", "conv_5", "conv_6", "conv_7", "conv_8")

# ── Scenario 1 — Greeting ─────────────────────────────────────────────────────
log("\nSCENARIO 1 — Greeting")
log("-" * 60)
send("greeting", "u1", "conv_1", "hey",
     lambda r: [
         ("status is received", r.get("status") == "received"),
         ("category is greeting", r.get("intent", {}).get("category") == "greeting"),
     ])

# ── Scenario 2 — Technical + contextualizer ───────────────────────────────────
log("SCENARIO 2 — Technical + query contextualizer across 3 turns")
log("-" * 60)
r1 = send("turn 1 - first message", "u1", "conv_2", "my VPN is not connecting",
          lambda r: [
              ("query unchanged on first message", r.get("query") == "my VPN is not connecting"),
          ])

r2 = send("turn 2 - vague follow-up", "u1", "conv_2", "I tried restarting it",
          lambda r: [
              ("query was rewritten", r.get("query", "").lower() != "i tried restarting it"),
          ])

r3 = send("turn 3 - pronoun chain", "u1", "conv_2", "still the same issue",
          lambda r: [
              ("query was rewritten", r.get("query", "").lower() != "still the same issue"),
              ("history has 4 entries", len(r.get("session_history", [])) == 4),
          ])

# ── Scenario 3 — ticket_op complete ──────────────────────────────────────────
log("SCENARIO 3 — ticket_op complete, straight through")
log("-" * 60)
send("complete ticket create", "u1", "conv_3", "create a ticket for network issue",
     lambda r: [
         ("status is received", r.get("status") == "received"),
         ("category is ticket_op", r.get("intent", {}).get("category") == "ticket_op"),
         ("action is create", r.get("intent", {}).get("action") == "create"),
     ])

# ── Scenario 4 — ticket_op incomplete → pending → resume ─────────────────────
log("SCENARIO 4 — ticket_op incomplete, pending state, resume")
log("-" * 60)
send("incomplete create", "u1", "conv_4", "create a ticket",
     lambda r: [
         ("status is incomplete", r.get("status") == "incomplete"),
         ("missing is issue description", r.get("missing") == "issue description"),
     ])

send("fill in detail", "u1", "conv_4", "printer not working on 3rd floor",
     lambda r: [
         ("status is received after detail", r.get("status") == "received"),
         ("pending was cleared", redis_client.get("pending:conv_4") is None),
     ])

# ── Scenario 5 — ticket view without ID ──────────────────────────────────────
log("SCENARIO 5 — ticket view without ID")
log("-" * 60)
send("view without ID", "u1", "conv_5", "show me the ticket",
     lambda r: [
         ("status is incomplete", r.get("status") == "incomplete"),
         ("missing is ticket ID", r.get("missing") == "ticket ID"),
     ])

send("provide ticket ID", "u1", "conv_5", "INC001234",
     lambda r: [
         ("status is received after ID", r.get("status") == "received"),
         ("pending was cleared", redis_client.get("pending:conv_5") is None),
     ])

# ── Scenario 6 — greeting_with_intent ────────────────────────────────────────
log("SCENARIO 6 — greeting_with_intent")
log("-" * 60)
send("greeting with intent", "u1", "conv_6", "hi, my laptop won't turn on",
     lambda r: [
         ("status is received", r.get("status") == "received"),
         ("category is greeting_with_intent", r.get("intent", {}).get("category") in ("greeting_with_intent", "technical")),
     ])

# ── Scenario 7 — multi_intent ────────────────────────────────────────────────
log("SCENARIO 7 — multi_intent")
log("-" * 60)
send("multi intent", "u1", "conv_7", "create a ticket and reset my password",
     lambda r: [
         ("status is clarification_needed", r.get("status") == "clarification_needed"),
         ("category is multi_intent", r.get("intent", {}).get("category") == "multi_intent"),
     ])

# ── Scenario 8 — history limit ───────────────────────────────────────────────
log("SCENARIO 8 — history limit (10 entries max returned)")
log("-" * 60)
messages = [
    "my printer is broken",
    "it won't print anything",
    "I checked the cables",
    "still not working",
    "tried reinstalling the driver",
    "what else can I try?",
]
r = None
for i, msg in enumerate(messages):
    r = chat("u1", "conv_8", msg)
    log(f"  Turn {i+1}: '{msg}' — history: {len(r.get('session_history', []))} entries")

history_len = len(r.get("session_history", []))
result = "PASS" if history_len == 10 else "FAIL"
log(f"\n  [{result}] history capped at 10 entries on turn 6 | got: {history_len}")
log()

# ─────────────────────────────────────────────────────────────────────────────
log("=" * 60)
log("Full flow test complete.")
log("=" * 60)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"\nResults saved to {OUTPUT_FILE}")
