import requests
import redis

BASE = "http://127.0.0.1:8000"
redis_client = redis.Redis.from_url("redis://localhost:6379", decode_responses=True)

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    result = "PASS" if condition else "FAIL"
    print(f"  [{result}] {label}")
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


print("\n" + "="*60)
print("TEST 1 — Redis connection")
print("="*60)
pong = redis_client.ping()
check("Redis is reachable", pong)


print("\n" + "="*60)
print("TEST 2 — session history persists in Redis")
print("="*60)
redis_client.delete("session:conv_r1")   # clean slate

chat("u123", "conv_r1", "my VPN is not working")
raw = redis_client.get("session:conv_r1")
check("session key created in Redis after first message", raw is not None)

import json
history = json.loads(raw)
check("history has 2 entries (user + assistant)", len(history) == 2)
check("first entry is user message", history[0]["role"] == "user")
check("second entry is assistant reply", history[1]["role"] == "assistant")


print("\n" + "="*60)
print("TEST 3 — history grows across turns")
print("="*60)
chat("u123", "conv_r1", "it still doesn't work")
history = json.loads(redis_client.get("session:conv_r1"))
check("history has 4 entries after second message", len(history) == 4)


print("\n" + "="*60)
print("TEST 4 — pending state saved and cleared")
print("="*60)
redis_client.delete("session:conv_r2")
redis_client.delete("pending:conv_r2")

chat("u123", "conv_r2", "create a ticket")
pending_raw = redis_client.get("pending:conv_r2")
check("pending key created after incomplete request", pending_raw is not None)

pending = json.loads(pending_raw)
check("pending intent is ticket_op", pending.get("category") == "ticket_op")

chat("u123", "conv_r2", "printer not working on 3rd floor")
pending_after = redis_client.get("pending:conv_r2")
check("pending key cleared after follow-up", pending_after is None)


print("\n" + "="*60)
print("TEST 5 — data survives between requests")
print("="*60)
r = chat("u123", "conv_r1", "how do I reset it?")
check("session_history returned has 4 entries from Redis", len(r.get("session_history", [])) == 4)


print("\n" + "="*60)
print(f"Total: {passed + failed} | Passed: {passed} | Failed: {failed}")
print("="*60 + "\n")