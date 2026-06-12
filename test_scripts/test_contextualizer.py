import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import requests
import redis
import json

BASE = "http://127.0.0.1:8000"
redis_client = redis.Redis.from_url("redis://localhost:6379", decode_responses=True)

passed = 0
failed = 0


def chat(user_id, conversation_id, message):
    return requests.post(f"{BASE}/chat", json={
        "user_id": user_id,
        "conversation_id": conversation_id,
        "message": message
    }).json()


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


def clean(conversation_id):
    redis_client.delete(f"session:{conversation_id}")
    redis_client.delete(f"pending:{conversation_id}")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 1 — first message, no history")
print("Expected: query returned unchanged (no LLM rewrite, nothing to use)")
print("="*60)
clean("conv_c1")
r = chat("u1", "conv_c1", "my printer is not working")
query = r.get("query", "")
original = "my printer is not working"
check("query field present in response", "query" in r)
check("query matches original message (no history to rewrite from)", query == original,
      f"original: '{original}' | got: '{query}'")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 2 — vague follow-up, history exists")
print("Expected: query rewritten to something specific")
print("="*60)
r = chat("u1", "conv_c1", "it still doesn't work")
query = r.get("query", "")
original = "it still doesn't work"
check("query field present in response", "query" in r)
check("query was rewritten (different from vague original)", query.lower() != original.lower(),
      f"original: '{original}' | rewritten to: '{query}'")
print(f"         rewritten query: '{query}'")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 3 — specific follow-up, history exists")
print("Expected: query enriched with context or returned as-is — either is valid")
print("="*60)
r = chat("u1", "conv_c1", "how do I restart the print spooler service?")
query = r.get("query", "")
original = "how do I restart the print spooler service?"
check("query field present in response", "query" in r)
check("query is non-empty and meaningful", len(query.strip()) > 0,
      f"original: '{original}' | got: '{query}'")
print(f"         query returned: '{query}'")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 4 — ticket_op skips contextualizer")
print("Expected: query equals original message exactly")
print("="*60)
clean("conv_c2")
r = chat("u1", "conv_c2", "create a ticket for VPN not connecting")
query = r.get("query", "")
original = "create a ticket for VPN not connecting"
check("query field present in response", "query" in r)
check("query unchanged for ticket_op (contextualizer not called)", query == original,
      f"original: '{original}' | got: '{query}'")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 5 — greeting skips contextualizer")
print("Expected: query equals original message exactly")
print("="*60)
clean("conv_c3")
r = chat("u1", "conv_c3", "hey")
query = r.get("query", "")
original = "hey"
check("query field present in response", "query" in r)
check("query unchanged for greeting (contextualizer not called)", query == original,
      f"original: '{original}' | got: '{query}'")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 6 — pronoun chain across multiple turns")
print("Expected: each vague message rewritten using accumulated history")
print("="*60)
clean("conv_c4")
chat("u1", "conv_c4", "my VPN is not connecting")
chat("u1", "conv_c4", "I tried restarting it")
r = chat("u1", "conv_c4", "still the same issue")
query = r.get("query", "")
original = "still the same issue"
check("query was rewritten", query.lower() != original.lower(),
      f"original: '{original}' | rewritten to: '{query}'")
print(f"         rewritten query: '{query}'")


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print(f"Total: {passed + failed} | Passed: {passed} | Failed: {failed}")
print("="*60 + "\n")
