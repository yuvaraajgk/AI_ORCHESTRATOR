# AIORC — AI Orchestrator

A FastAPI backend for an enterprise IT-support chatbot. Classifies incoming messages (greeting / technical question / ticket action), answers technical questions from a knowledge base via RAG, and creates/manages support tickets — all through one `POST /chat` endpoint. API-only; there is no bundled frontend (an Angular demo UI existed briefly for internal demonstration and was removed — see `DEVLOG.md` Day 24).

**Start here:**
- **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** — full architecture, every request flow explained in detail, known gaps and limitations. Read this to understand how the system actually works.
- **[DEVLOG.md](DEVLOG.md)** — the day-by-day build history, including dead ends and reverted decisions, if you want the *why* behind design choices.

## First-time setup (new machine)

**1. Backing services — three Docker containers.** The RAG one *must* use the `pgvector/pgvector` image, not vanilla `postgres` — that image doesn't have the vector extension binary, and `setup_rag_db.py`'s `CREATE EXTENSION vector` will fail against it.

```bash
docker run -d --name aiorc-postgres -e POSTGRES_USER=aiorc -e POSTGRES_PASSWORD=aiorc123 -e POSTGRES_DB=aiorc_db -p 5432:5432 postgres:latest
docker run -d --name aiorc-redis -p 6379:6379 redis:latest
docker run -d --name aiorc-rag -e POSTGRES_USER=aiorc -e POSTGRES_PASSWORD=aiorc123 -e POSTGRES_DB=aiorc_rag_db -p 5433:5432 pgvector/pgvector:pg17
```

**2. Python environment:**

```bash
python -m venv yenv                # a synced-over venv from another machine won't work — create fresh
./yenv/Scripts/Activate.ps1        # PowerShell
pip install -r requirements.txt
```

**3. Embedding model bootstrap — required before the next step.** `rag.py` and `seed_rag.py` both force `HF_HUB_OFFLINE=1` (so normal runs never touch the network), which means the very first run must fetch and cache the model *without* that flag set, or it'll fail with no obvious fix:

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)"
```

This downloads once into the local HuggingFace cache (`~/.cache/huggingface/`); every run after this works fully offline.

**4. Schema + knowledge base:**

```bash
python setup_db.py
python setup_rag_db.py
python seed_rag.py
```

**5. Environment variables:**

```bash
cp .env.example .env               # then fill in real values
```

## Running it (subsequent times)

```bash
docker start aiorc-postgres aiorc-redis aiorc-rag
./yenv/Scripts/Activate.ps1
uvicorn main:app --reload --reload-exclude yenv
```

Then open `http://127.0.0.1:8000/docs` for the API (Swagger UI), or `POST /chat` directly.

## Running tests

Everything under `test_scripts/` is a standalone script (not pytest) — run individually against the live server/dependencies:

```bash
python test_scripts/test_intent.py       # classifier accuracy + stability (no server needed, ~90 API calls)
python test_scripts/test_ticket.py       # ticket CRUD + the ticket-offer confirmation flow (server must be running)
python test_scripts/test_technical.py    # RAG + LLM grounded answers (server must be running)
python test_scripts/test_database.py     # Postgres integration (server must be running)
python test_scripts/test_redis.py        # Redis integration (server must be running)
python test_scripts/test_full_flow.py    # end-to-end scenarios (server must be running)
python test_scripts/test_contextualizer.py
python test_scripts/test_validation.py
```

`test_intent.py` in particular costs real API usage against the free-tier LLM provider — see the `RUNS_PER_CASE` constant at the top of the file if you want to reduce that cost.

## Project status

Functional end-to-end for its core scope (intent routing, RAG-grounded Q&A, ticket CRUD, conversation history). Not connected to real ServiceNow infrastructure — see `PROJECT_SUMMARY.md` §11 for the full list of known gaps and deliberate scope cuts.
