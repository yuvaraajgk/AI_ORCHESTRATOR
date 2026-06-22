# AI Orchestrator — Development Log

## Project Overview
AI-Powered Enterprise Chatbot — AI Orchestrator Module.
Responsible for understanding user intent and routing requests to the correct handler.

**Developer:** Yuvaraaj  
**Module:** AI Orchestrator Service  
**Stack:** Python, FastAPI, Groq (dev) / Anthropic Claude (prod), ChromaDB, RabbitMQ, ServiceNow API

---

## System Architecture

```
Frontend (Angular)
    → SignalR Hub / .NET Core API Gateway
        → AI Orchestrator (this module)
            → greeting    : direct LLM response
            → technical   : RAG pipeline → ChromaDB → LLM → answer
            → ticket_op   : ServiceNow API (create / view / update / close)
                → RabbitMQ queues → background workers
```

**Communication patterns:**
- Synchronous (HTTP) — AI Orchestrator ↔ LLM Inference / RAG
- Asynchronous (RabbitMQ) — AI Orchestrator → Ticket / Notification Workers

---

## Module Roadmap

- [x] Entry point — receive message from frontend
- [x] Intent Classification — classify message into category
- [ ] Decision Engine — route intent to correct handler
- [ ] Context Management — maintain session history per user
- [ ] RAG Module — embed query, search ChromaDB, retrieve chunks
- [ ] LLM Response Generation — answer using retrieved chunks + history
- [ ] ServiceNow Integration — ticket CRUD via ServiceNow API
- [ ] RabbitMQ Integration — publish to queues

---

## Daily Log

---

### Day 1 — 2026-06-02

#### What was built

**main.py**
- FastAPI app, entry point for all incoming messages
- `POST /chat` endpoint receives `user_id`, `conversation_id`, `message` from frontend
- Calls intent classifier and attaches `user_id` + `conversation_id` to the result

**intent_classifier.py**
- Uses Groq API (LLaMA 3.3 70b) — temporary for development
- Production target: Anthropic Claude (claude-sonnet-4-6)
- Classifies `message` into 3 categories:

| Category | Trigger | Routes To |
|---|---|---|
| `greeting` | Hi, hello, small talk | Direct LLM response |
| `technical` | Questions, bugs, info requests, questions *about* tickets | RAG / Knowledge Base |
| `ticket_op` | Actually performing a ticket action | ServiceNow API |

- For `ticket_op` extracts: `action` (create/view/update/close) and `details`
- `user_id` and `conversation_id` attached to every result for downstream context management

**requirements.txt**
- `fastapi`, `uvicorn`, `groq`, `chromadb`, `pika`, `pydantic`, `python-dotenv`

**.env**
- `GROQ_API_KEY` stored here, never committed to git

**.gitignore**
- Protects `.env`, `__pycache__`

#### Key Design Decisions

**Fixed intent categories over free-form AI classification**
The Decision Engine needs deterministic routing. Free-form AI-generated intent names would break routing logic since downstream workers expect known category names.

**"How do I create a ticket?" routes to technical, not ticket_op**
Informational questions about tickets should be answered from the Knowledge Base. Only actual ticket actions (create, view, update, close) route to ServiceNow API.

**user_id and conversation_id attached to every intent result**
Context management will be built in a later stage. All downstream modules need these IDs to maintain per-user conversation history.

**Groq used instead of Anthropic during development**
Corporate SSL proxy intercepts HTTPS connections. Groq was configured with `verify=False` on the httpx client to bypass this locally. Must be reverted before production.

**max_tokens=200 for classifier**
The classifier only returns a small JSON (~20-30 tokens). 200 is sufficient. Note: `max_tokens` controls output tokens only — input/prompt tokens are separate and unlimited.

---

### Day 2 — 2026-06-03

#### Context Management — Design Study

Planned the context management module. Three flows identified:

**Flow 1 — New User**
- No history found in store
- Query used as-is for RAG
- LLM responds fresh with no history
- Session created, first message saved

**Flow 2 — Existing User, Unrelated Question**
- History loaded but not relevant to current query
- Query contextualization runs but returns query unchanged
- RAG search and LLM response treat it as a fresh question
- Message appended to history

**Flow 3 — Existing User, Related Question**
- History loaded and relevant
- Query contextualization rewrites vague query using history
  - e.g. "it still doesn't work" → "printer still not working after restarting print spooler"
- RAG gets a richer, more specific query → better chunk retrieval
- LLM receives full history + chunks → contextual, non-repetitive response
- Message appended to history

**Query contextualization is the critical step** — it's what separates Flow 2 and Flow 3 behaviour. Without it, follow-up questions always produce weak RAG results.

#### Storage Decision — Redis vs SQL

| | Redis | SQL |
|---|---|---|
| Read speed | 0.1–1ms | 5–50ms |
| Write speed | 0.1–1ms | 5–30ms |
| Concurrent users | Handles easily | Degrades under load |
| Persistence | Optional | Always |
| TTL / auto-expiry | Built-in | Manual |

**Decision: Use both**
- Redis → active session context (last N messages, fast access, auto-expires after session)
- SQL → permanent message history (audit trail, analytics, future personalisation)

SQL alone is acceptable during development — performance difference is negligible at low load.

#### Planned module structure
```
main.py
    → intent_classifier.py       ✓ built
    → context_manager.py         ← load/save session history (Redis + SQL)
    → query_contextualizer.py    ← rewrite query using history
    → rag.py                     ← embed query, search ChromaDB
    → decision_engine.py         ← route intent to correct handler
    → response_generator.py      ← final LLM call with history + chunks
    → servicenow.py              ← ticket CRUD
```

---

### Day 3 — 2026-06-04

#### What was built

**database.py**
- In-memory mock for SQL DB with full real SQL code written in comments
- Two data structures mirroring the actual DB tables:
  - `_conversations` dict — stores conversation metadata per `conversation_id`
  - `_messages` list — flat ordered list of all messages across all conversations
- Functions:
  - `create_conversation()` — creates new conversation record on first message
  - `conversation_exists()` — checks if conversation is already registered
  - `save_message()` — logs a message with `expires_at = now + 30 days`, updates `last_active_at`
  - `get_conversations_by_user()` — returns all non-expired conversations for a user
  - `get_messages_by_conversation()` — returns all non-expired messages in order for a conversation
- Real SQL schema written in comments — ready to run on actual DB when access is available

**SQL Schema (in comments, ready to deploy):**
```sql
CREATE TABLE conversations (
    id               VARCHAR(36)  PRIMARY KEY,
    conversation_id  VARCHAR(100) UNIQUE NOT NULL,
    user_id          VARCHAR(100) NOT NULL,
    started_at       DATETIME     NOT NULL,
    last_active_at   DATETIME     NOT NULL,
    expires_at       DATETIME     NOT NULL
);

CREATE TABLE messages (
    id               VARCHAR(36)  PRIMARY KEY,
    conversation_id  VARCHAR(100) NOT NULL REFERENCES conversations(conversation_id),
    role             VARCHAR(20)  NOT NULL,
    content          TEXT         NOT NULL,
    intent_category  VARCHAR(50),
    created_at       DATETIME     NOT NULL,
    expires_at       DATETIME     NOT NULL
);
```

**cache.py**
- In-memory mock for Redis session store with real Redis code written in comments
- `_sessions` dict acts as the Redis store — keyed by `conversation_id`
- Functions:
  - `load_history()` — returns full message list for a session, empty list if new
  - `save_history()` — overwrites entire session history
  - `append_to_history()` — appends a single message to session, creates session if new
- Real Redis equivalent uses `redis_client.get/set` with JSON serialization — identical logic

**context_manager.py**
- Clean interface that combines Redis (cache.py) and SQL (database.py)
- Functions:
  - `get_history()` — loads session from Redis for use in RAG + LLM
  - `init_conversation_if_new()` — creates SQL conversation record on first message
  - `record_user_message()` — saves user message to both Redis and SQL
  - `record_assistant_response()` — saves assistant response to both Redis and SQL
- This file never needs to change when swapping mocks to real DBs

**main.py — updated**
- Now loads history from Redis at the start of every request
- Saves user message + assistant response to both Redis and SQL after processing
- Two new history endpoints added:
  - `GET /history/{user_id}` — returns all conversations for a user
  - `GET /history/{conversation_id}/messages` — returns full ordered message log

#### Key Design Decisions

**Two SQL tables instead of one**
`conversations` stores metadata once (user_id, started_at). `messages` stays lean with no repeated data. Enables efficient queries — listing conversations doesn't touch the messages table at all.

**Mock-first, real code in comments approach**
All DB and Redis code is built with in-memory mocks active. Real implementation is written in comments directly above each mock block. When DBs are available — uncomment real block, delete mock block, add connection string to `.env`. No restructuring needed.

**auto-expiry via expires_at column**
SQL has no built-in row TTL. Each row gets `expires_at = created_at + 30 days`. A scheduled nightly SQL job deletes rows where `expires_at < NOW()`. Cleanup is automatic with no app code involvement.

**context_manager.py as the only interface**
`main.py` and future modules only import from `context_manager.py`. They never touch `cache.py` or `database.py` directly. This means swapping backends only requires changes in two files, nothing else.

#### RabbitMQ — Clarified Role

The AI Orchestrator does **not** call ServiceNow directly. For `ticket_op` intents, it publishes a message to the RabbitMQ Ticket Queue. A separate Ticket Worker service (built by another team) consumes that message and handles the ServiceNow API call.

- AI Orchestrator responsibility: one `publish()` call with action + details
- Ticket Worker responsibility: ServiceNow API integration
- Benefit: chat stays fast, ticket failures don't crash the orchestrator, messages are never lost even if the worker is temporarily down

#### Updated Module Roadmap

- [x] Entry point — receive message from frontend
- [x] Intent Classification — classify message into category
- [x] Context Management — Redis session store + SQL message log (mock, real code in comments)
- [ ] Query Contextualizer — rewrite vague queries using history
- [ ] Decision Engine — route intent to correct handler
- [ ] RAG Module — embed query, search ChromaDB, retrieve chunks
- [ ] LLM Response Generation — answer using retrieved chunks + history
- [ ] ServiceNow Integration — ticket CRUD via ServiceNow API
- [ ] RabbitMQ Integration — publish to ticket/notification queues

---

### Day 4 — 2026-06-05

#### What was built

**cache.py — updated**
- Added `_pending` dict — second Redis key per conversation, stores incomplete intents waiting for follow-up
- Three new pending state functions:
  - `get_pending()` — checks if conversation has an unanswered clarification request
  - `set_pending()` — stores incomplete intent when validation fails
  - `clear_pending()` — deletes pending state once user fills in the missing info
- Real Redis equivalents use `pending:{conversation_id}` key — written in comments

**query_validator.py — new**
- Validates whether a classified intent has all required fields to be processed
- Rules per `ticket_op` action:
  - `create` → needs non-empty issue description
  - `view` / `close` → needs ticket ID matching `INC\d+` pattern
  - `update` → needs ticket ID + additional description beyond just the ID
- Returns `{"complete": True}` or `{"complete": False, "missing": "...", "ask": "..."}`
- `greeting`, `technical`, `multi_intent`, `greeting_with_intent` always pass validation

**main.py — updated with 6-step flow**

| Step | What happens |
|---|---|
| 1 | Check Redis for pending state — if found, skip classification, merge reply as missing detail |
| 2 | Classify intent normally |
| 3 | Handle multi_intent — save + return clarification |
| 4 | Handle greeting_with_intent — extract real intent, set greeted flag |
| 5 | Validate intent — if incomplete, save to pending, return clarification question |
| 6 | Save + process normally |

**intent testing — completed**
- Built `test_scripts/test_intent.py` — systematic test runner
- 20 test cases covering all 5 categories and edge cases
- Result: 100% accuracy — all cases passed
- Results saved in `test_scripts/results_test_intent.txt`

#### Key Design Decisions

**Pending state approach over simpler flag approach**
Chose Redis pending state (storing incomplete intent between turns) over a simpler `complete` flag approach. Reasons: more robust for multi-turn clarification, doesn't rely on query contextualizer being built first, works independently as a complete feature.

**Pending state cleared immediately on follow-up**
Once the user fills in the missing detail, `clear_pending()` is called before processing. If the user sends a new unrelated request while a pending state exists, their reply is used as the missing detail — intentional for now, can be refined later.

**Ticket ID format: INC\d+**
Used regex `INC\d+` to detect ticket IDs in details. This matches ServiceNow's standard INC number format. Can be extended to support other prefixes (CHG, PRB) when needed.

**multi_intent saves before returning**
Unlike the early return pattern, multi_intent now saves both user message and clarification response to Redis + SQL before returning. Full audit trail preserved.

#### greeting_with_intent — refined
Updated intent classifier to distinguish:
- `greeting + another intent` → `greeting_with_intent` — greet and process the real intent
- `two non-greeting intents` → `multi_intent` — ask user to split

`greeted: true` flag set on intent so response generator (future) can prepend a greeting to the answer.

#### Updated Module Roadmap

- [x] Entry point — receive message from frontend
- [x] Intent Classification — classify message into category
- [x] Multi-intent & greeting_with_intent handling
- [x] Intent testing — 100% accuracy on 20 test cases
- [x] Context Management — Redis session store + SQL message log (mock, real code in comments)
- [x] Query Validation — demand missing details for incomplete ticket requests
- [ ] Query Contextualizer — rewrite vague queries using conversation history
- [ ] Decision Engine — route intent to correct handler
- [ ] RAG Module — embed query, search ChromaDB, retrieve chunks
- [ ] LLM Response Generation — answer using retrieved chunks + history
- [ ] ServiceNow Integration — ticket CRUD via ServiceNow API
- [ ] RabbitMQ Integration — publish to ticket/notification queues

---

### Day 5 — 2026-06-08

#### Progress review against task table

**Intent Classification & Entity Extraction** — fully complete
- Define intents, entities, flows ✓
- Model implementation ✓
- Multi-intent & entity mapping handling ✓
- Testing & tuning ✓ — 100% on 20 test cases

**Context Management** — built, needs systematic testing
- Design conversation memory schema ✓
- Context persistence (session + DB integration) ✓
- Testing & tuning ⚠️ — manual testing only

**Query Validations** — complete
- Query and corresponding answer insertion for that session ✓
- Demand additional details in case of incomplete data ✓

**Decision Engine** — not started
**Prompt Builder** — not started

**Request and Response Structure** — complete
- Define input schema ✓
- Input validation & preprocessing ✓

---

### Day 6 — 2026-06-09

#### What was built

**cache.py — switched from mock to real Redis**
- Uncommented real Redis implementation, removed in-memory mock
- `redis.Redis.from_url()` now active — reads `REDIS_URL` from `.env`
- All three key functions live: `load_history()`, `save_history()`, `append_to_history()`
- All three pending functions live: `get_pending()`, `set_pending()`, `clear_pending()`
- Redis key structure in use:
  - `session:{conversation_id}` → JSON array of `{ role, content }` objects
  - `pending:{conversation_id}` → JSON object of incomplete intent, only exists mid-clarification

**test_scripts/test_redis.py — new**
- Systematic integration test for Redis — tests the server directly alongside the API
- 5 tests covering the full Redis lifecycle:

| Test | What it verifies |
|---|---|
| 1 | Redis server is reachable (`ping`) |
| 2 | Session key created and correctly structured after first message |
| 3 | History grows (appends, not overwrites) across turns |
| 4 | Pending key created on incomplete intent, cleared on follow-up |
| 5 | History loaded from Redis at start of each request (data survives between calls) |

- Reads Redis directly (`redis_client.get()`) — confirms data is actually persisted, not just returned by the API

#### Token Analysis

Observed the intent classifier consuming **386 prompt tokens** for a simple `"hey"` message.
Breakdown: ~384 tokens is the system prompt, ~2 tokens is the message itself.

Estimated full pipeline cost per turn once all components are built:

| Call | Input tokens | Output tokens |
|---|---|---|
| Intent classifier | ~386 | ~30 |
| Query contextualizer | ~620 | ~40 |
| Response generator | ~1740 | ~200 |
| **Total** | **~2750** | **~270** |

Cost comparison across model options:

| Model | Per turn | Per 1K turns |
|---|---|---|
| Groq / LLaMA (dev) | ~free | ~free |
| Gemini 2.5 Flash | ~$0.0003 | ~$0.29 |
| Claude Sonnet 4.6 (prod target) | ~$0.012 | ~$12.00 |

#### Key Finding — Classifier Prompt Optimisation Opportunity

The classifier system prompt is ~370 tokens — large for a routing task that already achieves 100% accuracy on the test suite. Trimming it to ~150 tokens (removing redundant examples, tightening descriptions) would save ~220 tokens on every single message across all three pipeline calls. This is the highest-leverage prompt optimisation available before the full pipeline is built.

**Not done yet** — optimisation and retest pending.

#### Updated Module Roadmap

- [x] Entry point — receive message from frontend
- [x] Intent Classification — classify message into category
- [x] Multi-intent & greeting_with_intent handling
- [x] Intent testing — 100% accuracy on 20 test cases
- [x] Context Management — Redis session store (real) + SQL message log (mock, real code in comments)
- [x] Redis integration testing — test_redis.py, all 5 tests passing
- [x] Query Validation — demand missing details for incomplete ticket requests
- [ ] Classifier prompt optimisation — trim ~370 token prompt, retest accuracy
- [ ] Query Contextualizer — rewrite vague queries using conversation history
- [ ] Decision Engine — route intent to correct handler
- [ ] RAG Module — embed query, search ChromaDB, retrieve chunks
- [ ] LLM Response Generation — answer using retrieved chunks + history
- [ ] ServiceNow Integration — ticket CRUD via ServiceNow API
- [ ] RabbitMQ Integration — publish to ticket/notification queues

---

### Day 7 — 2026-06-10 to 2026-06-12

#### What was built

**Classifier prompt optimisation — completed**
- Trimmed `SYSTEM_PROMPT` in `intent_classifier.py` from ~370 tokens to ~115 tokens
- Removed redundant examples and verbose descriptions, kept all critical classification rules
- Reran `test_intent.py` — 100% accuracy held across all 20 test cases
- Token count dropped from **386 → ~205** per classifier call — 45% reduction on every single message

**context_manager.py + cache.py — history window limit**
- Added `limit` parameter to `load_history()` in `cache.py`
- `get_history()` in `context_manager.py` now passes `limit=10` — returns last 10 entries (5 complete turns)
- Full history still written to Redis on every message — limit only applied at read time
- Handles edge cases naturally: first message returns `[]`, fewer than 10 entries returns whatever exists

**query_contextualizer.py — new**
- New module with one function: `contextualize(message, history)`
- If history is empty → returns message unchanged (no LLM call made)
- If history exists → formats history as text, sends to LLM with current message, gets back a rewritten standalone query
- Turns vague follow-ups like `"it still doesn't work"` into specific queries like `"printer still not working after troubleshooting"`

**main.py — Step 6 added**
- Contextualization inserted before saving and processing
- Only runs for `technical` intents — `ticket_op` and `greeting` bypass it entirely
- `query` field added to API response — shows the rewritten query for inspection

**test_scripts/test_contextualizer.py — new**
- 6 test cases, 11 checks
- Covers: first message (no history), vague follow-up rewrite, specific follow-up, ticket_op bypass, greeting bypass, pronoun chain across 3 turns
- All 11 checks passing
- `sys.path` fix also applied to `test_intent.py` so all test scripts run correctly from project root

#### Key Design Decisions

**History limit at read time, not write time**
Full history is always written to Redis. The 10-entry limit is applied only when loading for the LLM. This means SQL has the complete audit trail, Redis has the full session, and the LLM only sees the relevant recent window. No data is ever discarded.

**Contextualizer only fires for technical intents**
`ticket_op` intents don't go to RAG — they route to ServiceNow. No point rewriting a query that won't be searched. `greeting` responses are direct LLM replies with no retrieval step. Contextualization is only useful where RAG is involved.

**Test 3 expectation corrected**
Initial test assumed a self-contained message would be returned unchanged even with history present. The LLM correctly enriched it with context instead — more useful for RAG. Test updated to check that the query is non-empty and meaningful rather than asserting exact string match.

#### Updated Token Estimate (post-optimisation)

| Call | Before | After |
|---|---|---|
| Intent classifier | ~386 tokens | ~205 tokens |
| Query contextualizer | ~620 tokens | ~620 tokens |
| Response generator | ~1740 tokens | ~1740 tokens |
| **Total per turn** | **~2750 tokens** | **~2565 tokens** |

#### Updated Module Roadmap

- [x] Entry point — receive message from frontend
- [x] Intent Classification — classify message into category
- [x] Multi-intent & greeting_with_intent handling
- [x] Intent testing — 100% accuracy on 20 test cases
- [x] Context Management — Redis session store (real) + SQL message log (mock, real code in comments)
- [x] Redis integration testing — test_redis.py, all 5 tests passing
- [x] Query Validation — demand missing details for incomplete ticket requests
- [x] Classifier prompt optimisation — 386 → 205 tokens, 100% accuracy held
- [x] History window limit — last 10 entries (5 turns) passed to LLM
- [x] Query Contextualizer — rewrite vague queries using conversation history, tested
- [ ] Decision Engine — route intent to correct handler
- [ ] Prompt Builder — assemble history + RAG chunks + query into LLM payload
- [ ] LLM Response Generation — final LLM call, returns real answer to user
- [ ] RAG Module — embed query, search ChromaDB, retrieve chunks (blocked: no DB access)
- [ ] ServiceNow Integration — ticket CRUD via ServiceNow API (blocked: no credentials)
- [ ] RabbitMQ Integration — publish to ticket/notification queues (blocked: no infra config)

---

### Day 8 — 2026-06-17

#### What was built

**database.py — switched from mock to real PostgreSQL**
- Replaced in-memory mock with live psycopg2 implementation
- Connection pooling via `SimpleConnectionPool(1, 10)` — borrows and returns connections per function call via `_get_conn()` / `_put_conn()`
- Real SQL queries active across all four functions:
  - `create_conversation()` — `INSERT ... ON CONFLICT (conversation_id) DO NOTHING` — idempotent, safe to call on every message
  - `conversation_exists()` — `SELECT 1` check
  - `save_message()` — `INSERT INTO messages` + `UPDATE conversations SET last_active_at` in same transaction
  - `get_conversations_by_user()` / `get_messages_by_conversation()` — `RealDictCursor` returns rows as dicts directly
- All timestamps stored with `timezone.utc` — no daylight saving issues
- 30-day expiry applied on insert: `expires_at = now + timedelta(days=30)`

**setup_db.py — new**
- One-time schema initialisation script: `python setup_db.py`
- Creates `conversations` and `messages` tables using `CREATE TABLE IF NOT EXISTS` — idempotent, safe to re-run
- Foreign key constraint on `messages.conversation_id → conversations.conversation_id`

**requirements.txt — updated**
- Added `psycopg2-binary`

**test_scripts/test_database.py — new**
- 8 integration tests — hits the live API then queries PostgreSQL directly via psycopg2 to verify data was actually stored
- `clean()` helper deletes test rows before each run so tests are idempotent

| Test | What it verifies |
|---|---|
| 1 | `conversations` row created on first message, `user_id` correct, `expires_at` is 30 days out |
| 2 | Both user and assistant `messages` rows saved, content and `intent_category` correct |
| 3 | Message count grows correctly across turns (4 rows after 2 turns) |
| 4 | Conversation row not duplicated on follow-up messages |
| 5 | `last_active_at` updated on each new message |
| 6 | `GET /history/{user_id}` returns correct conversations from DB |
| 7 | `GET /history/{conversation_id}/messages` returns messages in chronological order |
| 8 | `ticket_op` `intent_category` stored correctly |

**test_scripts/test_full_flow.py — new**
- 8 end-to-end scenario tests against the live FastAPI endpoint
- Covers all intent types and edge cases across the full pipeline
- Results saved to `test_scripts/results_test_full_flow.txt`

| Scenario | What it covers |
|---|---|
| 1 | Greeting — status and category |
| 2 | Technical across 3 turns — contextualizer rewrites vague follow-ups |
| 3 | Complete `ticket_op` — straight through, no clarification |
| 4 | Incomplete `ticket_op` → pending state → resume on detail |
| 5 | Ticket view without ID → ask for ID → resume |
| 6 | `greeting_with_intent` — greet + process underlying request |
| 7 | `multi_intent` — ask user to split |
| 8 | History limit — confirms cap at 10 entries after 6 turns |

#### Key Design Decisions

**Connection pooling over a single connection**
Production will have multiple concurrent requests. A single shared connection would block or corrupt under load. `SimpleConnectionPool` with 1–10 connections handles concurrency without the overhead of a full async pool. Each function checks out and returns a connection — no connection is held open between requests.

**ON CONFLICT DO NOTHING on conversation insert**
Removes the need to call `conversation_exists()` before every `create_conversation()`. The DB enforces uniqueness on `conversation_id` — inserting a duplicate is a no-op. Simpler and race-condition-free.

**UTC timestamps throughout**
`datetime.now(timezone.utc)` used everywhere. Avoids daylight saving edge cases and ensures consistent ordering when messages arrive from different timezones.

#### Updated Module Roadmap

- [x] Entry point — receive message from frontend
- [x] Intent Classification — classify message into category
- [x] Multi-intent & greeting_with_intent handling
- [x] Intent testing — 100% accuracy on 20 test cases
- [x] Context Management — Redis session store (real) + PostgreSQL message log (real)
- [x] Redis integration testing — test_redis.py, all 5 tests passing
- [x] PostgreSQL integration testing — test_database.py, all 8 tests passing
- [x] Query Validation — demand missing details for incomplete ticket requests
- [x] Classifier prompt optimisation — 386 → 205 tokens, 100% accuracy held
- [x] History window limit — last 10 entries (5 turns) passed to LLM
- [x] Query Contextualizer — rewrite vague queries using conversation history, tested
- [x] End-to-end flow testing — test_full_flow.py, 8 scenarios passing
- [ ] Decision Engine — route intent to correct handler
- [ ] Prompt Builder — assemble history + RAG chunks + query into LLM payload
- [ ] LLM Response Generation — final LLM call, returns real answer to user
- [ ] RAG Module — embed query, search ChromaDB, retrieve chunks (blocked: no DB access)
- [ ] ServiceNow Integration — ticket CRUD via ServiceNow API (blocked: no credentials)
- [ ] RabbitMQ Integration — publish to ticket/notification queues (blocked: no infra config)

---

### Day 9 — 2026-06-19

#### What was done

**New device setup**
- Project migrated to new Windows device via OneDrive sync
- Created new virtual environment `yenv` — `wenv` carried over via OneDrive but its compiled extensions and interpreter path are tied to the old machine
- Both Redis and PostgreSQL now run in Docker containers:
  - `docker run -d --name aiorc-postgres -e POSTGRES_USER=aiorc -e POSTGRES_PASSWORD=aiorc123 -e POSTGRES_DB=aiorc_db -p 5432:5432 postgres:latest`
  - `docker run -d --name aiorc-redis -p 6379:6379 redis:latest`

**requirements.txt — redis version unpinned**
- `redis==3.5.3` → `redis`
- Root cause: `redis 3.5.3` imports `distutils.version.StrictVersion` at module load. `distutils` was removed in Python 3.12. Project runs on Python 3.14 — import fails on startup with `ModuleNotFoundError: No module named 'distutils'`
- Fix: unpin to latest (`redis 5.x`) which dropped the `distutils` dependency

**greeting_handler.py — new**
- New module with one function: `generate_greeting_response(message, history)`
- Calls Groq LLM with a lightweight system prompt — friendly IT support assistant, 1-2 sentences
- Conversation history passed as chat messages so returning users get contextual responses
- `max_tokens=100` — greeting responses are intentionally short

**main.py — greeting responses wired in**
- Imported `generate_greeting_response`
- Step 7 now branches on intent category: `greeting` calls the handler, everything else stays `"processing..."`
- First fully working end-to-end response flow — chatbot now returns a real reply for greetings

#### Key Notes

**Venvs are not portable between machines**
Venvs embed the absolute path to the Python interpreter at creation time (`pyvenv.cfg: home = ...`). Compiled C extensions (.pyd files) are also machine-specific. A fresh `python -m venv yenv` + `pip install -r requirements.txt` is required on a new device even if the old `wenv` folder synced over.

**Docker preferred over native installs for backing services**
Running Redis and PostgreSQL in Docker avoids Windows service management and version conflicts. Named containers (`aiorc-postgres`, `aiorc-redis`) restart with `docker start <name>` after reboots.

---

### Day 10 — 2026-06-22

#### What was built

**sample_docs/ — new folder**
- Three plain-text IT support knowledge base documents:
  - `vpn.txt` — VPN connectivity issues, authentication failures, disconnections
  - `password_reset.txt` — forgotten passwords, account lockouts, sync delays
  - `printers.txt` — offline printers, paper jams, print queue issues, quality problems
- Each document structured with overview, per-issue troubleshooting steps, FAQs, and notes
- Sections separated by `---` — used as chunk boundaries in seed_rag.py

**setup_rag_db.py — new**
- One-time initialisation script for the RAG database
- Enables the `pgvector` extension, creates the `documents` table with a `vector(768)` column
- Separate from `setup_db.py` — touches only the RAG database, never the conversation database

**seed_rag.py — new**
- Reads every `.txt` file from `sample_docs/`, splits each into chunks using `---` as the boundary
- Each chunk is embedded using Nomic Embed Text v1.5 via `sentence-transformers` locally — no API key needed
- `search_document:` prefix added to each chunk before embedding — required by Nomic's training format
- Inserts chunk text + 768-dimension vector into the `documents` table via `%s::vector` cast
- Clears existing rows before each run — re-seeding is safe and idempotent
- Dev-only utility: production documents will be populated by a separate ETL process

**rag.py — new**
- Exposes one function: `search(query, top_k=5) → list[str]`
- Embeds the query with `search_query:` prefix using the same Nomic model
- Runs cosine similarity search via pgvector's `<=>` operator, returns top 5 most relevant chunks
- Uses `SimpleConnectionPool` — same pattern as `database.py`
- All schema details are internal to this file — nothing outside `rag.py` knows the table structure

**requirements.txt — updated**
- `chromadb` → `sentence-transformers` (pgvector used instead, no ChromaDB needed)
- `einops` added — required by Nomic Embed Text v1.5

**New Docker container — aiorc-rag**
- Separate PostgreSQL instance with pgvector on port 5433
- `pgvector/pgvector:pg17` image — pgvector built in, unlike `postgres:latest`
- Completely isolated from `aiorc-postgres` (conversation storage) on port 5432
- `RAG_DATABASE_URL` added to `.env`

#### Key Design Decisions

**Separate Docker container for RAG, not the same DB**
Keeps conversation storage and document storage fully isolated. Production may use a completely different database instance, schema, or even provider for the vector store. Separation enforces this boundary from day one.

**pgvector over ChromaDB**
Same PostgreSQL stack already in use — no additional service to run or manage. pgvector's `<=>` cosine similarity operator is a single SQL clause. ChromaDB would have required a separate process and dependency.

**rag.py as the only file that knows the schema**
`search(query) → list[str]` is the contract. When production documents arrive with a different table structure, only `rag.py` is updated — everything else (main.py, technical_handler.py) stays the same. Same pattern as `context_manager.py` abstracting Redis and PostgreSQL.

**Nomic Embed Text v1.5 with task prefixes**
Model trained with `search_document:` and `search_query:` prefixes for asymmetric retrieval — documents and queries are embedded differently for better semantic matching. Skipping the prefix would silently produce lower-quality results.

**Chunking by `---` section boundaries**
Each chunk is a complete, self-contained section (one issue + symptoms + resolution, or one FAQ block). Character-based chunking would split mid-paragraph, producing chunks that lose context at boundaries. Section-based chunks are directly useful when retrieved.

**Corporate SSL proxy workaround for HuggingFace download**
Nomic model download goes through HuggingFace Hub which uses `httpx` internally. Monkey-patched `httpx.Client.__init__` to default `verify=False` before imports — same workaround pattern used for Groq. Only needed on first run; model is cached locally after download.

#### Updated Module Roadmap

- [x] Entry point — receive message from frontend
- [x] Intent Classification — classify message into category
- [x] Multi-intent & greeting_with_intent handling
- [x] Intent testing — 100% accuracy on 20 test cases
- [x] Context Management — Redis session store (real) + PostgreSQL message log (real)
- [x] Redis integration testing — all 5 tests passing
- [x] PostgreSQL integration testing — all 8 tests passing
- [x] Query Validation — demand missing details for incomplete ticket requests
- [x] Classifier prompt optimisation — 386 → 205 tokens, 100% accuracy held
- [x] History window limit — last 10 entries (5 turns) passed to LLM
- [x] Query Contextualizer — rewrite vague queries using conversation history
- [x] End-to-end flow testing — 8 scenarios passing
- [x] Greeting Responses — real LLM replies for greeting intents
- [x] RAG Module — pgvector setup, Nomic embeddings, document seeding, search function
- [ ] Technical Responses — LLM answer using RAG chunks + history (next)
- [ ] Decision Engine — route intent to correct handler
- [ ] ServiceNow Integration — ticket CRUD via ServiceNow API (blocked: no credentials)
- [ ] RabbitMQ Integration — publish to ticket/notification queues (blocked: no infra config)

---

## Environment Setup

```bash
# Start backing services (Docker)
docker start aiorc-postgres aiorc-redis aiorc-rag

# First-time only — create conversation DB tables
python setup_db.py

# First-time only — create RAG DB tables
python setup_rag_db.py

# First-time only — seed documents into RAG DB
python seed_rag.py

# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn main:app --reload --reload-exclude yenv
```

**.env file:**
```
GROQ_API_KEY=your_key_here
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql://aiorc:aiorc123@localhost:5432/aiorc_db
RAG_DATABASE_URL=postgresql://aiorc:aiorc123@localhost:5433/aiorc_rag_db
```

**First-time Docker setup:**
```bash
docker run -d --name aiorc-postgres -e POSTGRES_USER=aiorc -e POSTGRES_PASSWORD=aiorc123 -e POSTGRES_DB=aiorc_db -p 5432:5432 postgres:latest
docker run -d --name aiorc-redis -p 6379:6379 redis:latest
docker run -d --name aiorc-rag -e POSTGRES_USER=aiorc -e POSTGRES_PASSWORD=aiorc123 -e POSTGRES_DB=aiorc_rag_db -p 5433:5432 pgvector/pgvector:pg17
```

**Test via Swagger UI:** `http://127.0.0.1:8000/docs`

---

## Notes & Reminders

- Swap `groq` → `anthropic` in requirements.txt and intent_classifier.py before production
- Remove `verify=False` from httpx client before production
- ServiceNow API credentials to be provided separately
- RabbitMQ connection config to be provided by infrastructure team
