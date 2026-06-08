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

## Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn main:app --reload
```

**.env file:**
```
GROQ_API_KEY=your_key_here
```

**Test via Swagger UI:** `http://127.0.0.1:8000/docs`

---

## Notes & Reminders

- Swap `groq` → `anthropic` in requirements.txt and intent_classifier.py before production
- Remove `verify=False` from httpx client before production
- Redis setup needed before context management module is built
- ServiceNow API credentials to be provided separately
- RabbitMQ connection config to be provided by infrastructure team
