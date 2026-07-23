import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from intent_classifier import classify_intent

# The classifier is not fully deterministic even at temperature=0 — the same
# 20 cases scored anywhere from 85% to 95% across identical back-to-back runs
# during live testing (2026-07-16), due to non-associative floating point in
# the provider's batched inference. Running each case multiple times measures
# real stability instead of one-shot luck. This multiplies API usage by
# RUNS_PER_CASE — lower it if you're watching your free-tier neuron budget.
RUNS_PER_CASE = 3

test_cases = [
    # (query, expected_category, expected_action)

    # ── greeting ──────────────────────────────────────────────────────────
    ("hey",                                          "greeting",             None),
    ("good morning",                                 "greeting",             None),
    ("helo",                                         "greeting",             None),
    ("how are you?",                                 "greeting",             None),
    ("yo",                                           "greeting",             None),
    ("sup",                                          "greeting",             None),

    # ── technical ─────────────────────────────────────────────────────────
    ("my laptop won't turn on",                      "technical",            None),
    ("how do I reset my password?",                  "technical",            None),
    ("how do I raise a ticket?",                     "technical",            None),
    ("VPN is not connecting",                        "technical",            None),
    ("it's not working",                             "technical",            None),
    ("URGENT my system crashed",                     "technical",            None),
    ("not working",                                  "technical",            None),
    ("cant login pls help",                          "technical",            None),
    ("wifi dead again ugh",                          "technical",            None),
    # regression — this exact phrasing was misclassified as multi_intent in
    # production (2026-07-16): a single continuous follow-up describing prior
    # troubleshooting attempts is still ONE technical intent, not multiple
    ("i did all of the measures, none of it works , what to do now?", "technical", None),
    # negation — contains ticket_op-shaped keywords but explicitly declines the action
    ("don't create a ticket, just tell me how to fix the VPN issue", "technical", None),

    # ── ticket_op ─────────────────────────────────────────────────────────
    ("create a ticket for network issue",            "ticket_op",            "create"),
    ("show me ticket INC001234",                     "ticket_op",            "view"),
    ("close ticket INC005678",                       "ticket_op",            "close"),
    ("update ticket INC009 with new info",           "ticket_op",            "update"),
    ("is there an update on INC001234?",             "ticket_op",            "view"),
    ("can you check on my ticket?",                  "ticket_op",            "view"),
    ("close inc0000123",                             "ticket_op",            "close"),

    # ── greeting_with_intent ──────────────────────────────────────────────
    ("hi, my VPN is down",                           "greeting_with_intent", None),
    ("hello, create a ticket for printer issue",     "greeting_with_intent", None),
    ("hey how's it going, how do I reset password",  "greeting_with_intent", None),

    # ── multi_intent ──────────────────────────────────────────────────────
    ("create a ticket and reset my password",        "multi_intent",         None),
    ("fix my VPN and also show me ticket INC001",    "multi_intent",         None),
]

# boundary/degenerate inputs — there's no single "correct" category for these,
# so they're checked only for not crashing and returning a recognized
# category, not for an exact match
KNOWN_CATEGORIES = {"greeting", "technical", "ticket_op", "multi_intent", "greeting_with_intent"}
boundary_cases = ["", "   ", "👍"]

total_case_runs = 0
total_case_passes = 0
stable_count = 0
flaky_count = 0
failed_count = 0

print(f"\n{'Query':<68} {'Expected':<25} {'Rate':<8} {'Result'}")
print("-" * 130)

for query, expected_category, expected_action in test_cases:
    hits = 0
    last_seen = None

    for _ in range(RUNS_PER_CASE):
        try:
            result = classify_intent(query)
            got_category = result.get("category")
            got_action = result.get("action")
            last_seen = got_category + (f"/{got_action}" if got_action else "")

            category_match = got_category == expected_category
            action_match = (expected_action is None) or (got_action == expected_action)
            if category_match and action_match:
                hits += 1
        except Exception as e:
            last_seen = f"ERROR: {e}"

    total_case_runs += RUNS_PER_CASE
    total_case_passes += hits

    rate_str = f"{hits}/{RUNS_PER_CASE}"
    if hits == RUNS_PER_CASE:
        status = "STABLE PASS"
        stable_count += 1
    elif hits == 0:
        status = "FAIL"
        failed_count += 1
    else:
        status = "FLAKY"
        flaky_count += 1

    expected_str = expected_category + (f"/{expected_action}" if expected_action else "")
    display_query = query if len(query) <= 66 else query[:63] + "..."
    print(f"{display_query:<68} {expected_str:<25} {rate_str:<8} {status} (last: {last_seen})")

print("-" * 130)
print(f"\nCases: {len(test_cases)} | Stable: {stable_count} | Flaky: {flaky_count} | Failed: {failed_count}")
print(f"Total runs: {total_case_runs} | Total passes: {total_case_passes}")
print(f"Aggregate accuracy: {round(total_case_passes / total_case_runs * 100, 1)}%\n")

# ── boundary/degenerate inputs ─────────────────────────────────────────────
print(f"\n{'Boundary input':<30} {'Result'}")
print("-" * 60)

boundary_ok = 0
for query in boundary_cases:
    label = repr(query)
    try:
        result = classify_intent(query)
        category = result.get("category")
        if category in KNOWN_CATEGORIES:
            print(f"{label:<30} OK — returned recognized category: {category!r}")
            boundary_ok += 1
        else:
            print(f"{label:<30} FAIL — unrecognized category: {category!r}")
    except Exception as e:
        print(f"{label:<30} FAIL — raised {e.__class__.__name__}: {e}")

print("-" * 60)
print(f"\nBoundary inputs handled without crashing: {boundary_ok}/{len(boundary_cases)}\n")
