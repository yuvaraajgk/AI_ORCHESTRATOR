import requests

BASE = "http://127.0.0.1:8000"


def chat(user_id, conversation_id, message):
    res = requests.post(f"{BASE}/chat", json={
        "user_id": user_id,
        "conversation_id": conversation_id,
        "message": message
    })
    return res.json()


def check(label, response, expected_status, expected_response_contains=None):
    status_ok = response.get("status") == expected_status
    content_ok = True
    if expected_response_contains:
        content_ok = expected_response_contains.lower() in response.get("response", "").lower()

    result = "PASS" if (status_ok and content_ok) else "FAIL"
    print(f"  [{result}] {label}")
    if result == "FAIL":
        print(f"         expected status: {expected_status} | got: {response.get('status')}")
        if expected_response_contains:
            print(f"         expected response to contain: '{expected_response_contains}'")
            print(f"         got: '{response.get('response')}'")
    return result == "PASS"


passed = 0
failed = 0


def run(label, response, expected_status, expected_response_contains=None):
    global passed, failed
    if check(label, response, expected_status, expected_response_contains):
        passed += 1
    else:
        failed += 1


print("\n" + "="*60)
print("TEST 1 — ticket create without details (should ask for issue)")
print("="*60)
r = chat("u123", "conv_t1", "create a ticket")
run("status is incomplete",           r, "incomplete")
run("asks for issue description",     r, "incomplete", "issue")

print("\nRedis pending set — now send the missing detail:")
r = chat("u123", "conv_t1", "printer not working on 3rd floor")
run("status is received after detail", r, "received")
run("intent is ticket_op",             r, "received")
print(f"  intent details: {r.get('intent', {}).get('details')}")


print("\n" + "="*60)
print("TEST 2 — ticket view without ID (should ask for ticket ID)")
print("="*60)
r = chat("u123", "conv_t2", "show me the ticket")
run("status is incomplete",      r, "incomplete")
run("asks for ticket ID",        r, "incomplete", "INC")

print("\nRedis pending set — now send the ticket ID:")
r = chat("u123", "conv_t2", "INC001234")
run("status is received after ID", r, "received")


print("\n" + "="*60)
print("TEST 3 — ticket update with ID but no changes (should ask what to change)")
print("="*60)
r = chat("u123", "conv_t3", "update ticket INC005678")
run("status is incomplete",          r, "incomplete")
run("asks for update description",   r, "incomplete", "changes")

print("\nRedis pending set — now send the changes:")
r = chat("u123", "conv_t3", "change priority to high")
run("status is received after detail", r, "received")


print("\n" + "="*60)
print("TEST 4 — complete request (should go straight through)")
print("="*60)
r = chat("u123", "conv_t4", "create a ticket for VPN not connecting")
run("status is received directly", r, "received")
run("no incomplete step needed",   r, "received")


print("\n" + "="*60)
print("TEST 5 — Redis memory check (history grows across turns)")
print("="*60)
chat("u123", "conv_t5", "my printer is not working")
chat("u123", "conv_t5", "it still doesn't work")
r = chat("u123", "conv_t5", "how do I reset it?")
history_len = len(r.get("session_history", []))
result = "PASS" if history_len == 4 else "FAIL"
print(f"  [{result}] history has 4 messages before 3rd send | got: {history_len}")
if result == "PASS":
    passed += 1
else:
    failed += 1


print("\n" + "="*60)
print(f"Total: {passed + failed} | Passed: {passed} | Failed: {failed}")
print("="*60 + "\n")
