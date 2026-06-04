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
