import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import requests
import redis

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


def no_kb_reference(response):
    lowered = response.lower()
    return "knowledge base" not in lowered and "excerpt" not in lowered


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 1 — VPN troubleshooting question")
print("Expected: relevant VPN answer, no KB references in response")
print("="*60)
clean("tech_t1")
r = chat("u1", "tech_t1", "my vpn is not connecting")
response = r.get("response", "")
print(f"  Response preview: {response[:120]}...")
check("response is non-empty", len(response.strip()) > 0)
check("response does not reference knowledge base or excerpts", no_kb_reference(response))
check("response contains VPN-related content",
      any(w in response.lower() for w in ["vpn", "connect", "network", "internet", "wi-fi"]))


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 2 — Password reset question")
print("Expected: relevant password answer, no KB references")
print("="*60)
clean("tech_t2")
r = chat("u1", "tech_t2", "I forgot my password and can't log in")
response = r.get("response", "")
print(f"  Response preview: {response[:120]}...")
check("response is non-empty", len(response.strip()) > 0)
check("response does not reference knowledge base or excerpts", no_kb_reference(response))
check("response contains password-related content",
      any(w in response.lower() for w in ["password", "reset", "account", "login", "log in", "mfa"]))


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 3 — Printer offline question")
print("Expected: relevant printer answer, no KB references")
print("="*60)
clean("tech_t3")
r = chat("u1", "tech_t3", "my printer is showing as offline")
response = r.get("response", "")
print(f"  Response preview: {response[:120]}...")
check("response is non-empty", len(response.strip()) > 0)
check("response does not reference knowledge base or excerpts", no_kb_reference(response))
check("response contains printer-related content",
      any(w in response.lower() for w in ["printer", "print", "offline", "spooler", "queue"]))


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 4 — Software installation question")
print("Expected: relevant software answer, no KB references")
print("="*60)
clean("tech_t4")
r = chat("u1", "tech_t4", "I'm getting an error when trying to install software")
response = r.get("response", "")
print(f"  Response preview: {response[:120]}...")
check("response is non-empty", len(response.strip()) > 0)
check("response does not reference knowledge base or excerpts", no_kb_reference(response))
check("response contains software-related content",
      any(w in response.lower() for w in ["software", "install", "application", "administrator", "service desk"]))


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 5 — Email/Outlook question")
print("Expected: relevant email answer, no KB references")
print("="*60)
clean("tech_t5")
r = chat("u1", "tech_t5", "my outlook is not receiving any emails")
response = r.get("response", "")
print(f"  Response preview: {response[:120]}...")
check("response is non-empty", len(response.strip()) > 0)
check("response does not reference knowledge base or excerpts", no_kb_reference(response))
check("response contains email-related content",
      any(w in response.lower() for w in ["email", "outlook", "inbox", "receive", "junk", "send/receive"]))


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 6 — Question outside knowledge base")
print("Expected: offers to raise a ticket instead of hallucinating an answer")
print("="*60)
clean("tech_t6")
r = chat("u1", "tech_t6", "how do I book a conference room?")
response = r.get("response", "")
print(f"  Response preview: {response[:120]}...")
check("response is non-empty", len(response.strip()) > 0)
# unlike TESTS 1-5 (real grounded answers, where the LLM leaking "based on the
# knowledge base..." would be a genuine instruction leak), this scenario
# legitimately produces the fixed TICKET_OFFER_MESSAGE, which intentionally
# says "knowledge base" as real user-facing copy — not a check to apply here
check("response offers to raise a ticket rather than answering",
      "raise a ticket" in response.lower())
check("response directs to IT Service Desk or states no information available",
      any(w in response.lower() for w in ["service desk", "contact", "don't have", "do not have",
                                           "reach out", "not available", "unable to"]))


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 7 — greeting_with_intent (greeting + technical question)")
print("Expected: response starts with 'Hello!' and answers the VPN question")
print("="*60)
clean("tech_t7")
r = chat("u1", "tech_t7", "hi, my vpn is not working")
response = r.get("response", "")
print(f"  Response preview: {response[:120]}...")
check("response is non-empty", len(response.strip()) > 0)
check("response starts with Hello! (greeted flag applied)",
      response.startswith("Hello!"), f"got: '{response[:40]}'")
check("response contains VPN-related content",
      any(w in response.lower() for w in ["vpn", "connect", "network", "internet"]))


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("TEST 8 — multi-turn topic shift (VPN -> Email)")
print("Expected: second response addresses email, not VPN")
print("="*60)
clean("tech_t8")
chat("u1", "tech_t8", "my vpn is not connecting")
r = chat("u1", "tech_t8", "now my outlook is also not working, emails are not coming in")
response = r.get("response", "")
print(f"  Response preview: {response[:120]}...")
check("response is non-empty", len(response.strip()) > 0)
check("response does not reference knowledge base or excerpts", no_kb_reference(response))
check("response addresses email issue",
      any(w in response.lower() for w in ["email", "outlook", "inbox", "receive", "junk"]))


# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print(f"Total: {passed + failed} | Passed: {passed} | Failed: {failed}")
print("="*60 + "\n")
