import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from intent_classifier import classify_intent

test_cases = [
    # (query, expected_category, expected_action)
    # greeting
    ("hey",                                          "greeting",             None),
    ("good morning",                                 "greeting",             None),
    ("helo",                                         "greeting",             None),
    ("how are you?",                                 "greeting",             None),

    # technical
    ("my laptop won't turn on",                      "technical",            None),
    ("how do I reset my password?",                  "technical",            None),
    ("how do I raise a ticket?",                     "technical",            None),
    ("VPN is not connecting",                        "technical",            None),
    ("it's not working",                             "technical",            None),
    ("URGENT my system crashed",                     "technical",            None),
    ("not working",                                  "technical",            None),

    # ticket_op
    ("create a ticket for network issue",            "ticket_op",            "create"),
    ("show me ticket INC001234",                     "ticket_op",            "view"),
    ("close ticket INC005678",                       "ticket_op",            "close"),
    ("update ticket INC009 with new info",           "ticket_op",            "update"),

    # greeting_with_intent
    ("hi, my VPN is down",                           "greeting_with_intent", None),
    ("hello, create a ticket for printer issue",     "greeting_with_intent", None),
    ("hey how's it going, how do I reset password",  "greeting_with_intent", None),

    # multi_intent
    ("create a ticket and reset my password",        "multi_intent",         None),
    ("fix my VPN and also show me ticket INC001",    "multi_intent",         None),
]

passed = 0
failed = 0
errors = 0

print(f"\n{'Query':<50} {'Expected':<25} {'Got':<25} {'Result'}")
print("-" * 115)

for query, expected_category, expected_action in test_cases:
    try:
        result = classify_intent(query)
        got_category = result.get("category")
        got_action   = result.get("action")

        category_match = got_category == expected_category
        action_match   = (expected_action is None) or (got_action == expected_action)

        if category_match and action_match:
            status = "PASS"
            passed += 1
        else:
            status = "FAIL"
            failed += 1

        expected_str = expected_category + (f"/{expected_action}" if expected_action else "")
        got_str      = got_category + (f"/{got_action}" if got_action else "")
        print(f"{query:<50} {expected_str:<25} {got_str:<25} {status}")

    except Exception as e:
        errors += 1
        print(f"{query:<50} {expected_category:<25} ERROR: {e}")

print("-" * 115)
print(f"\nTotal: {len(test_cases)} | Passed: {passed} | Failed: {failed} | Errors: {errors}")
print(f"Accuracy: {round(passed / len(test_cases) * 100, 1)}%\n")