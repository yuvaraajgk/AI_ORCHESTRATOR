# AIORC — Project Summary & Handoff

This document explains what the AI Orchestrator (AIORC) is, how it's built, and exactly how every message flows through it — written for a developer picking up this module fresh. For the day-by-day story of *why* things ended up this way (including dead ends and reverted attempts), see `DEVLOG.md`. This document only describes the system as it exists **now**.


## 1. Overview

AIORC is a **FastAPI backend, API-only** — it has no bundled frontend. It exposes three kinds of capability behind one endpoint: answering IT-support questions from a knowledge base, creating/managing support tickets, and just chatting. A caller sends a plain-text message to `POST /chat`; AIORC figures out *what kind of request this actually is* (an LLM call), then routes it to the right handler, and always remembers the conversation (Redis for the live session, Postgres for the permanent record). A minimal Angular demo UI existed briefly for internal demonstration purposes and was removed once it had served that purpose — see `DEVLOG.md` Day 24. The intended production caller is a separate Angular/SignalR frontend owned by another team (see the original architecture note in `DEVLOG.md`'s early entries), which this repo was never meant to include.

There is no authentication layer yet — every request carries a `user_id` and `conversation_id` supplied by the caller, trusted as-is.

## 2. Architecture

```
Any HTTP client
    │  POST /chat  { user_id, conversation_id, message }
    ▼
FastAPI app (main.py)
    │
    ├─► intent_classifier.py ──► llm_client.py ──► Cloudflare Workers AI
    │        (classifies the message, with a deterministic correction pass)
    │
    ├─► context_manager.py ──┬─► cache.py (Redis)       — live session history + pending state
    │                        └─► database.py (Postgres)  — permanent conversation/message log
    │
    ├─► query_validator.py                              — is this ticket_op intent complete enough to act on?
    ├─► query_contextualizer.py ──► llm_client.py         — rewrite vague follow-ups (technical only)
    ├─► greeting_handler.py ──► llm_client.py
    ├─► technical_handler.py ──┬─► rag.py (pgvector)     — knowledge base search
    │                          └─► (offers a ticket on KB gap, doesn't create one directly)
    └─► ticket_handler.py ──► database.py (tickets table)
```

Three separate Postgres databases/containers are in play:
- **Conversation DB** (`DATABASE_URL`) — `conversations`, `messages`, `tickets` tables
- **RAG DB** (`RAG_DATABASE_URL`) — separate Postgres instance with the `pgvector` extension, holds only the `documents` table
- **Redis** (`REDIS_URL`) — live session cache, not persisted long-term

They're deliberately isolated (see `DEVLOG.md` Day 10) so the vector store could later live on entirely different infrastructure without touching conversation storage.

## 3. File-by-file responsibility map

| File | Responsibility |
|---|---|
| `main.py` | FastAPI app — the `/chat` endpoint and its full routing logic, plus `/history/*` |
| `intent_classifier.py` | Classifies a message into a category via LLM, plus a deterministic post-classification correction layer |
| `llm_client.py` | The one shared LLM client (Cloudflare) and all retry logic — nothing else should construct its own client |
| `context_manager.py` | The *only* interface `main.py` uses for history/persistence — abstracts over `cache.py` + `database.py` |
| `cache.py` | Redis: session history (`session:{id}`) and pending clarification state (`pending:{id}`, TTL'd) |
| `database.py` | Postgres: `conversations` and `messages` tables |
| `query_validator.py` | Deterministic (non-LLM) checks: is a `ticket_op` intent complete? Is a reply affirmative? |
| `query_contextualizer.py` | Rewrites vague technical follow-ups ("it's still broken") into standalone queries, using history |
| `greeting_handler.py` | Generates a warm, short LLM reply for `greeting` intents |
| `technical_handler.py` | RAG search → grounded LLM answer, or offers a ticket if the KB has nothing relevant |
| `ticket_handler.py` | All ticket CRUD against Postgres, INC-ID generation, response text formatting |
| `rag.py` | Embeds text (Nomic, local model) and does cosine-similarity search / insert against pgvector |
| `seed_rag.py` | One-time/repeatable script: chunks `sample_docs/*.txt` and indexes them into pgvector |
| `setup_db.py` / `setup_rag_db.py` | One-time schema creation for the two Postgres databases |
| `test_scripts/` | Ad-hoc integration test scripts (not pytest) — see §11 for coverage gaps |

## 4. The core request flow — `POST /chat`

Every message goes through `main.py`'s `receive_message()`, in this order:

**Step 0 — load history.** `get_history(conversation_id)` pulls the last 10 messages (5 turns) from Redis. Empty on a new conversation.

**Step 1 — check for pending state.** Two *different* kinds of "waiting for a reply" state can exist in Redis under `pending:{conversation_id}`, distinguished by `category`:

- `"ticket_offer"` — the previous turn asked "want me to raise a ticket for this?". This message is treated as a yes/no answer (`is_affirmative()`, deterministic keyword check), never re-classified. Yes → ticket created via `create_kb_gap_ticket()`. No/anything else → politely declines. Either way, this **returns immediately** — the rest of the pipeline below doesn't run.
- Anything else (a genuine incomplete `ticket_op`, e.g. missing a ticket ID) — this message is treated as the missing field, merged into the stashed intent (`pending["details"] = message`), and processing continues from Step 6 below (classification is skipped).

If neither applies, classification runs normally:

**Step 2 — classify.** `classify_intent(message)` → one of `greeting`, `technical`, `ticket_op`, `multi_intent`, `greeting_with_intent`. See §5 for what each does and §9 for how classification actually works internally.

**Step 3 — multi_intent short-circuit.** Two independent requests bundled in one message → ask the user to send them separately, save both sides of the exchange, **return immediately**.

**Step 4 — greeting_with_intent unwrap.** `{"category": "greeting_with_intent", "other": {...}}` → unwrap `other` into the working `intent`, set `greeted = True` so the eventual response gets a `"Hello! "` prefix. If `other` is missing entirely (a real failure mode seen in production — see `DEVLOG.md` Day 21), falls back to a plain `greeting` rather than crashing.

**Step 5 — validation.** `validate_intent()` (in `query_validator.py`) checks whether a `ticket_op` intent has everything it needs (ticket ID for view/close/update, a description for create). If not, the intent is stashed in `pending`, the user is asked for the missing piece, and this **returns immediately**. Their next message re-enters at Step 1 and resumes here.

**Step 6 — contextualize (technical only).** `contextualize()` rewrites vague follow-ups using history. Skipped entirely (no LLM call) if there's no history yet.

**Step 7 — dispatch and respond.** The user message is saved first, then routed:
- `greeting` → `generate_greeting_response()`
- `technical` → `generate_technical_response()` — may also stash a new `ticket_offer` pending state (see §5)
- `ticket_op` → `handle_ticket_op()`
- anything else (a classifier category that isn't one of the three above — shouldn't happen, but defended against) → logs it server-side and returns a generic "could you rephrase that?" instead of crashing

The assistant's reply is saved, and the full response — `status`, resolved `intent`, `query`, `session_history`, `response` — goes back to the caller.

## 5. Every intent, in detail

### `greeting`
Simplest path. `generate_greeting_response(message, history)` sends the message plus recent history to the LLM with a short, warm system prompt (`greeting_handler.py`). No database writes beyond the standard message log, no RAG.

### `technical`
The richest path (`technical_handler.py`):
1. `query_contextualizer.contextualize()` may have already rewritten the query (Step 6 above).
2. `rag.search(query)` embeds the query locally and returns the top 5 chunks + their cosine distances from pgvector.
3. **Branch on relevance** — if there are no chunks, or the best match's distance exceeds `KB_GAP_THRESHOLD = 0.5`: return `TICKET_OFFER_MESSAGE` ("I don't have information on that... want me to raise a ticket?") and signal `main.py` to stash a `ticket_offer` pending state. **No ticket is created at this point** — only offered.
4. Otherwise, the retrieved chunks + system prompt + history + query go to the LLM. The system prompt explicitly forbids inventing information and instructs the model to reply with the exact string `NOT_FOUND` if the retrieved content still doesn't actually answer the question. If it does return `NOT_FOUND`, that's treated identically to case 3 above — offer a ticket, don't just say "I don't know."

`generate_technical_response()` returns `(answer, offer_query)` — `offer_query` is `None` unless an offer was made, and `main.py` is what actually writes the pending state (the handler doesn't touch Redis directly).

**Important nuance:** if the KB *does* have a real, relevant answer, and that answer's own content happens to say "if this persists, contact the IT Service Desk" (several `sample_docs/*.txt` files end their troubleshooting steps this way), that is **not** the ticket-offer flow — it's a legitimate grounded answer that happens to recommend escalation. The offer only fires when the KB genuinely has nothing, not whenever "IT Service Desk" appears in a reply.

### `ticket_op`
Routes to `handle_ticket_op()` in `ticket_handler.py` — see §6 for full detail on each action.

### `multi_intent`
Detected when the message bundles two genuinely independent requests (not just a message that mentions several things — see the system prompt in `intent_classifier.py` for the exact boundary, which took several iterations to get right; a single continuous technical follow-up describing multiple prior troubleshooting steps is *not* multi-intent). Response: ask the user to send them one at a time. No handler module involved — the response text is inline in `main.py`.

### `greeting_with_intent`
A greeting plus a real request in one message ("hi, my VPN is down"). Unwrapped in Step 4 above; processed as whatever the inner intent is, with a `"Hello! "` prefix on the final response.

### The pending-confirmation flows (not "intents" per se, but real conversational states)
Two distinct multi-turn flows exist, both implemented via the same Redis `pending:{conversation_id}` mechanism but handled by different code paths:
1. **Incomplete `ticket_op`** — "close my ticket" with no ID → asks for the ID → next message fills it in → resumes normal processing as if it had been complete from the start.
2. **`ticket_offer` confirmation** — the KB found nothing → asks "want a ticket?" → next message is a yes/no, intercepted *before* classification (Step 1a in `main.py`), never sent to the classifier at all.

## 6. The ticket system

**Schema** (`setup_db.py`, conversation DB):
```sql
CREATE TABLE tickets (
    id               VARCHAR(36)   PRIMARY KEY,
    ticket_id        VARCHAR(20)   UNIQUE NOT NULL,   -- e.g. INC0000042
    user_id          VARCHAR(100)  NOT NULL,
    conversation_id  VARCHAR(100)  NOT NULL,
    status           VARCHAR(20)   NOT NULL DEFAULT 'open',  -- open | in_progress | closed
    description      TEXT          NOT NULL,
    resolution       TEXT,
    kb_gap           BOOLEAN       NOT NULL DEFAULT FALSE,
    original_query   TEXT,
    created_at       TIMESTAMP     NOT NULL,
    updated_at       TIMESTAMP     NOT NULL
)
```

**ID generation**: `_generate_ticket_id()` calls `nextval('ticket_id_seq')` — a real Postgres sequence (`setup_db.py`), zero-padded to 7 digits (`INC0000001`, `INC0000002`, ...). This used to be `COUNT(*) + 1`, which is not just a theoretical concurrency risk — it broke under completely sequential, single-user testing the moment any row was ever deleted (which test cleanup does constantly), since the count drops but already-issued IDs elsewhere in the table don't free up. Migrated to a sequence, which is atomic and monotonic regardless of deletes or concurrency. `create_ticket()` also rolls back on failure before returning its connection to the pool — the original `COUNT(*)` collision left a poisoned, unrolled-back connection sitting in the shared pool, which would have caused confusing, unrelated-looking failures for whatever request borrowed it next.

**The four actions** (`handle_ticket_op()`):
| Action | What it does |
|---|---|
| `create` | Inserts a row, returns the new INC ID |
| `view` | Fetches by ID (`get_ticket()`), returns status/description/timestamps formatted as text |
| `update` | Extracts the ID via regex from the free-text `details`, appends the remainder to `description`, sets status → `in_progress` |
| `close` | Sets status → `closed` |

**KB-gap tickets specifically** go through `create_kb_gap_ticket()` (a separate entry point from `handle_ticket_op`, called directly by `main.py`'s ticket-offer confirmation flow, not by the classifier) — same underlying `create_ticket()`, but always sets `kb_gap=True` and `original_query`, so these are distinguishable from user-initiated tickets in the data.

**Why `ticket_op` detection is partly deterministic, not pure LLM judgment**: the classifier reliably recognizes `view`/`close`/`update` when a ticket ID anchors the message, but was found to unreliably classify two patterns as `technical` instead: `create` requests (which structurally can never have an ID, since the ticket doesn't exist yet) and status-check questions phrased as questions rather than commands ("is there an update on INC001234?"). Rather than keep patching the LLM prompt (which caused regressions elsewhere twice), `intent_classifier.py` has a `_correct_technical_misclassification()` function that runs *after* the LLM responds — if and only if the LLM said `technical`, it checks for an `INC\d+` pattern or an imperative create-ticket pattern via regex and overrides accordingly. This never touches a correct `multi_intent` or `ticket_op` call from the LLM, only corrects a specific known-wrong `technical` guess. Zero added prompt tokens; fully deterministic where it applies.

## 7. The RAG (knowledge base) system

**Embedding model**: `nomic-ai/nomic-embed-text-v1.5` via `sentence-transformers`, running **locally** (no API call, no cost, but adds real CPU/load time on process start — this is why every fresh Python process in this project takes several seconds to import `rag.py` or anything that imports it transitively).

**Hard requirement, not just a config detail**: the RAG Postgres container must run the `pgvector/pgvector:pg17` image specifically — `setup_rag_db.py`'s `CREATE EXTENSION vector` fails against a vanilla `postgres` image, which doesn't ship the extension binary at all. Both `rag.py` and `seed_rag.py` also force `HF_HUB_OFFLINE=1` before importing `sentence_transformers`, so the embedding model must already be in the local HuggingFace cache — a genuinely fresh machine needs one un-flagged run to download it first, or every RAG operation fails outright. See `README.md`'s first-time setup for both.

**Asymmetric prefixes matter**: documents are embedded with `search_document:` prepended, queries with `search_query:` — this is how Nomic's model was trained, and skipping the prefix silently degrades match quality rather than erroring.

**Schema** (`setup_rag_db.py`, separate RAG database):
```sql
CREATE TABLE documents (
    id        SERIAL PRIMARY KEY,
    source    TEXT,
    content   TEXT,
    embedding vector(768)
)
```

**Search** (`rag.py`): `search(query, top_k=5)` returns `(chunks, scores)` — cosine distance via pgvector's `<=>` operator, ascending (lower = more similar). `0.0` = identical, higher = less similar. `KB_GAP_THRESHOLD = 0.5` in `technical_handler.py` is the cutoff for "close enough to answer from."

**Seeding** (`seed_rag.py`): reads every `.txt` in `sample_docs/`, splits on `---` as the chunk boundary, embeds and inserts each chunk. Re-running it is safe — it deletes only the rows for that specific `source` before re-inserting, not the whole table (this was a real bug once; see `DEVLOG.md` Day 17).

**Current content**: 5 topics (`vpn`, `password_reset`, `printers`, `email_issues`, `software_installation`), 48 chunks total. All hand-written sample docs, not real ingested KB articles.

**What's *not* built**: there used to be a `/kb/resolved` endpoint meant to close the loop — take a resolved KB-gap ticket and embed its resolution back into pgvector so the same question gets answered directly next time. It was removed (along with `/kb/search`) because nothing actually called it — no ServiceNow webhook, no manual workflow. `rag.insert_document()` still exists and still works (used by `seed_rag.py`), so re-adding that loop later is a matter of wiring a caller to it again, not rebuilding it.

## 8. Context & session management

Two storage layers, one abstraction:

- **`cache.py` (Redis)** — `session:{conversation_id}` holds the full message list as JSON (read with an optional `limit`, always written in full — the 10-entry cap is applied at read time only, so nothing is ever discarded). `pending:{conversation_id}` holds whichever pending state is active (see §5), with a `PENDING_TTL_SECONDS = 300` expiry so an abandoned clarification can't hijack an unrelated message days later.
- **`database.py` (Postgres)** — `conversations` (one row per conversation, created idempotently via `ON CONFLICT DO NOTHING`) and `messages` (append-only log, every row 30-day TTL via an `expires_at` column — there's no automatic cleanup job, expired rows just get filtered out of queries, so a scheduled deletion job would need to be added separately if storage growth becomes a concern).
- **`context_manager.py`** — the *only* thing `main.py` (and any future caller) should import for history. `record_user_message()` and `record_assistant_response()` each write to both Redis and Postgres in one call. This is the seam if either storage backend is ever swapped out.

## 9. The LLM provider layer

**Current provider**: Cloudflare Workers AI, model `@cf/meta/llama-3.1-8b-instruct-fast`, configured entirely via `.env` (`CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_MODEL`). This project has changed LLM provider **four times** (Groq → Ollama → Cerebras → Cloudflare) — every time due to either a corporate network policy block or the specific model being deprecated server-side without warning. See `DEVLOG.md` for the full history. **Do not hardcode a model ID anywhere without checking the provider's live docs first** — two of those five migrations broke because a "current" model turned out to already be deprecated.

**`llm_client.py`** is the single shared client all four LLM-calling modules use — nothing else should construct its own `OpenAI(...)` client. It provides:
- `create_with_retry(messages, max_tokens, **kwargs)` — wraps the raw API call, retries with backoff (4s/8s) on `RateLimitError`, `APIStatusError`, or `APIConnectionError`. This exists because Cerebras/Cloudflare's free-tier queues occasionally reject requests outright under load rather than just being slow.
- `complete(messages, max_tokens)` — calls the above, and *additionally* retries (2s/4s) if the response comes back with empty/`None` content, which has also been observed under load, separately from an outright error.

`intent_classifier.py` uses `create_with_retry` directly (it needs the raw response to parse JSON out of, with its own retry loop for malformed/truncated JSON on top). `greeting_handler.py`, `query_contextualizer.py`, and `technical_handler.py` all use `complete()`.

**Classification is not fully deterministic**, even with `temperature=0` set on the classifier call — measured, back-to-back, on the same 20-case test suite with zero code changes between runs: 85%, 85%, 95%. This is a known characteristic of hosted, batched LLM inference (floating-point non-associativity across a provider's batched requests), not something fixable from the client side. `test_scripts/test_intent.py` runs each case 3× and reports a stability rate for this reason, not a single pass/fail.

## 10. Setup & running it locally

Full first-time setup (Docker container creation, the embedding-model bootstrap step, schema, seeding) is in `README.md` — that's the canonical copy-pasteable version, kept in one place rather than duplicated here. Short version once that's done once:

```bash
docker start aiorc-postgres aiorc-redis aiorc-rag
./yenv/Scripts/Activate.ps1
uvicorn main:app --reload --reload-exclude yenv
```

Then open `http://127.0.0.1:8000/docs` for the API (Swagger UI), or call `POST /chat` directly — there's no frontend in this repo.

Required `.env` keys (copy from `.env.example`): `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_MODEL`, `REDIS_URL`, `DATABASE_URL`, `RAG_DATABASE_URL`.

## 11. Known gaps, limitations, and traps

**Not built (blocked externally, not a code gap):**
- ServiceNow integration — no real external ticketing system, `tickets` table is the only source of truth

**Real, open bugs/gaps as of this writing:**
- A specific classifier failure mode is unfixed: casual/informal phrasing containing words like "ugh" gets misclassified as `greeting` even when the rest of the message is a clear technical complaint (e.g. `"my wifi is dead again ugh"`). Diagnosed as the model over-weighting tone over content; no clean deterministic fix exists for this one (unlike the `ticket_op` cases in §6) since there's no bounded keyword signal to correct on. Candidate fixes: another prompt example (risk: has caused regressions elsewhere twice already), or trying a larger/different classifier model.
- `httpx.Client(verify=False)` in `llm_client.py` — a corporate-SSL-proxy workaround for local dev. **Must be removed before any real deployment.**
- `wenv/` (a stale venv from a previous machine) and `dump.rdb` (a local Redis snapshot) are still sitting in the project folder, gitignored but present — harmless but confusing clutter if this folder is ever handed over as a raw copy rather than a clean `git clone`.
- The same "no rollback before returning the connection to the pool" pattern that was fixed in `create_ticket()` (see §6) likely also exists in `update_ticket()`, `close_ticket()`, and the write functions in `database.py` — only `create_ticket()` was fixed, since that's the one an actual bug surfaced in. Worth auditing the rest before relying on this under real concurrent load.

**Design decisions, not bugs:**
- `pending:*` Redis keys expire after 5 minutes (`PENDING_TTL_SECONDS`) — an abandoned clarification or ticket-offer just silently lapses back to normal classification, by design.
- Messages "expire" via an `expires_at` column after 30 days, but nothing actually deletes them — expired rows are just excluded from query results. A real cleanup job would need to be added if storage growth matters.
