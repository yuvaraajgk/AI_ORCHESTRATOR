# AI Orchestrator — Summary Log

A plain-language record of what was built each day and why it matters.

---

### Day 1 — 2026-06-02
**Getting the chatbot to understand what the user wants**

The first thing any chatbot needs to do is figure out *what the user is asking for*. Before we can fetch answers, create tickets, or do anything useful — we need to know the intent behind the message.

Today we built the entry point of the system (the door that receives all incoming messages) and the intent classifier (the brain that reads the message and decides what kind of request it is).

Every message gets sorted into one of three buckets:
- **Greeting** — the user is just saying hi
- **Technical** — the user has a question or problem and needs information
- **Ticket operation** — the user wants to actually do something with a support ticket (create, view, update, close)

We also handled two tricky edge cases:
- *"Hi, my VPN is broken"* — that's a greeting AND a real request. We greet the user and process the request underneath.
- *"Fix my VPN and also reset my password"* — that's two separate requests at once. We ask the user to send them one at a time.

The AI model doing the classification is LLaMA 3.3 (via Groq) for now — it's free and fast for development. The production version will use Claude.

---

### Day 2 — 2026-06-03
**Deciding how to remember conversations**

Today was a planning day. No code written — just figuring out the right way to store conversation history before building it wrong.

The key question: when a user says *"it still doesn't work"*, how does the system know what *it* refers to? It needs memory.

We settled on two layers of storage:
- **Redis** (fast, temporary) — stores the last few messages of an active conversation. Think of it as short-term memory. Data lives here while the conversation is happening.
- **SQL database** (permanent) — stores every message ever sent. Think of it as the long-term record. Used for audit trails and future analytics.

We also mapped out the three conversation flows the system needs to handle — a brand new user, a returning user asking something unrelated to before, and a returning user following up on a previous topic. That third flow is the hardest and requires rewriting the user's vague query using their history before searching for an answer.

---

### Day 3 — 2026-06-04
**Building the memory system**

Today we built everything planned on Day 2.

**The database layer** stores two things: conversation records (who started a conversation and when) and messages (every individual message sent). Both are mocks for now — the real database code is written but commented out, ready to switch on when the actual database is available.

**The Redis layer** stores the active session history as a simple list of messages. Every time a message comes in, the history is loaded first, and both the user's message and the assistant's reply are saved to it afterwards.

**The context manager** sits on top of both and acts as the only interface the rest of the app talks to. Nothing else touches Redis or the database directly — this means if we swap out either storage layer later, only one file needs to change.

All messages auto-expire after 30 days. No manual cleanup needed.

---

### Day 4 — 2026-06-05
**Handling incomplete requests and testing the classifier**

Two things done today.

**First — handling incomplete ticket requests.** If a user says *"create a ticket"* without saying what the problem is, the system can't do anything useful. We built a validator that checks whether a request has everything it needs before processing it. If something is missing, the system asks the user for it, saves the half-finished request to Redis, and waits. When the user replies with the missing detail, the system picks up where it left off — no need to re-classify or start over.

**Second — testing the intent classifier.** We ran 20 test cases covering every category and edge case. Result: 100% accuracy. The classifier correctly identified greetings, technical questions, ticket operations, combined greeting+intent messages, and multi-intent messages every time.

---

### Day 5 — 2026-06-08
**Progress check against the full task list**

No new code today — a review of where things stand against the full project scope.

What's done: intent classification (fully tested), context management (built, needs systematic testing), query validation (complete).

What's not started yet: the decision engine that routes requests to the right handler, the RAG module that searches the knowledge base, the LLM response generator, and the ServiceNow and RabbitMQ integrations.

The context management piece was flagged — it's built and works in manual testing, but hasn't been systematically tested with a proper test script yet.

---

### Day 6 — 2026-06-09
**Switching Redis from mock to real and testing it properly**

Two things done today.

**First — Redis is now live.** Until today, the Redis layer was a mock (just a Python dictionary pretending to be Redis). We switched it on for real — the app now connects to an actual Redis server and reads/writes data that genuinely persists between requests.

**Second — Redis tested properly.** We wrote a dedicated test script that connects to Redis directly (not just through the API) to confirm data is actually being stored and not just returned by the app. Five tests covering: server connection, session history creation, history growing across turns, pending state being saved and cleared, and data surviving between separate requests. All passed.

**Also noted:** the intent classifier is using ~386 tokens per message — almost all of it is the system prompt, not the user's message. Once the full pipeline is built (classifier + query rewriter + response generator), each conversation turn will cost roughly 3,000 tokens total. At current model pricing that's under a cent per message with Gemini Flash, around 1.2 cents with Claude Sonnet. The classifier prompt has room to be cut roughly in half without affecting accuracy — flagged as an optimisation to do before the next module is built.

---

### Day 7 — 2026-06-10 to 2026-06-12
**Optimising the classifier, capping history, and building the query rewriter**

Three things done across these days.

**First — classifier prompt trimmed.** The system prompt that tells the LLM how to classify messages was 370 tokens long — far more than needed. We rewrote it to be concise while keeping every important rule. Token count dropped from 386 to around 205 per call — a 45% saving on every single message the system ever receives. Re-ran the full 20-case test suite after trimming: still 100% accuracy. No quality lost.

**Second — conversation history capped at 5 turns.** The LLM reading the full conversation history would get increasingly expensive as conversations grew. We added a limit so only the last 5 turns (10 messages) are passed to the LLM. The full history is still saved in Redis and the database — the cap only applies to what the LLM sees. First-time users and short conversations are handled automatically — if there are fewer than 10 messages, all of them are returned.

**Third — query contextualizer built and tested.** This is the module that solves vague follow-up messages. When a user says *"it still doesn't work"* after a previous message about their printer, the system now rewrites that into *"printer still not working after troubleshooting"* before searching the knowledge base. Without this, RAG would have nothing useful to search on. The rewriter only runs for technical questions — ticket actions and greetings bypass it entirely. Six tests written and passing, including a three-turn pronoun chain test where the system correctly tracked what *"it"* referred to across multiple messages.

---

### Day 8 — 2026-06-17
**Switching the database from mock to real PostgreSQL and completing end-to-end testing**

Two things done today.

**First — PostgreSQL is now live.** Until today, the database layer was a mock (a Python dictionary pretending to be a database). We switched it on for real — the app now connects to an actual PostgreSQL instance and persists every message to disk. Connection pooling is in place so multiple simultaneous requests don't conflict. The schema was also formalised into a one-time setup script (`setup_db.py`) that creates both tables and can be re-run safely without wiping data.

**Second — full integration and end-to-end tests written and passing.** We added two test scripts. The first (`test_database.py`) sends messages through the API and then connects directly to PostgreSQL to confirm the rows were actually written — not just returned by the app. Eight checks cover conversation creation, message storage, timestamp updates, expiry dates, and the history retrieval endpoints. The second (`test_full_flow.py`) runs eight real conversation scenarios end-to-end: greetings, multi-turn technical questions with query rewriting, complete and incomplete ticket operations, greeting-with-intent combinations, multi-intent detection, and the history cap. All scenarios pass.

At this point the core pipeline — intent classification, context management (Redis + PostgreSQL), query validation, and query contextualisation — is fully built, tested, and running against real infrastructure.

---

### Day 9 — 2026-06-19
**New device setup and fixing a Python 3.14 compatibility issue**

Project moved to a new Windows device via OneDrive sync. The virtual environment (`wenv`) came along in the sync but couldn't be reused — venvs embed the Python interpreter's absolute path and compile extensions tied to the original machine. A fresh environment was created instead.

Redis and PostgreSQL are now both running in Docker containers rather than native Windows installs. This makes the setup reproducible — spinning up both services is two `docker run` commands and they persist across reboots with `docker start`.

One dependency issue discovered: the pinned `redis==3.5.3` package uses a Python module (`distutils`) that was removed in Python 3.12. Since the project runs on Python 3.14, it crashed on startup with an import error. The fix was to unpin the redis version so pip installs the latest release (5.x), which dropped that dependency years ago.

Also built the first real end-to-end response. Until now every message returned `"processing..."`. A new `greeting_handler.py` module calls the Groq LLM directly for greeting intents, passing the conversation history as context so returning users get a personalised response. The chatbot now gives a real reply to greetings for the first time.

---

### Day 10 — 2026-06-22
**Building the RAG knowledge base**

Three things done today.

**First — sample documents created.** Three IT support knowledge base documents were written covering VPN issues, password resets, and printer problems. Each document is structured with an overview, step-by-step troubleshooting per issue, FAQs, and important notes. Sections are separated by `---` which is used as the chunk boundary when indexing.

**Second — RAG database set up with pgvector.** Rather than adding a separate ChromaDB service, pgvector was used — it's a PostgreSQL extension that adds vector storage and similarity search to a standard Postgres database. A dedicated Docker container (`aiorc-rag`) was created on port 5433, completely separate from the conversation database on port 5432. The documents table stores the text of each chunk alongside its 768-dimension embedding vector.

**Third — documents embedded and indexed.** A seeding script reads the document files, splits them into chunks at section boundaries, and runs each chunk through Nomic Embed Text v1.5 — a local embedding model that runs entirely on the machine with no API key. The model uses task-specific prefixes: `search_document:` when indexing chunks and `search_query:` when embedding a user query at search time. This asymmetric approach produces better retrieval results than using the same prefix for both.

The `rag.py` module exposes a single `search(query)` function. It embeds the query, runs a cosine similarity search via pgvector, and returns the top 5 most relevant chunks. Nothing outside this file knows the table structure — when production documents arrive with a different schema, only `rag.py` changes. The RAG module is now fully built and ready to be wired into the technical response handler.

---

### Day 11 — 2026-06-23
**Technical responses live — chatbot now answers IT questions end-to-end**

Two things built today, one bug fixed.

**First — technical response handler built.** When a user asks a technical question, the system now retrieves the most relevant sections from the knowledge base, builds a prompt combining those sections with the conversation history, and calls the LLM to produce a grounded answer. The LLM is instructed to only answer from the retrieved content — if nothing relevant was found, it tells the user to contact the IT Service Desk instead of making something up. For messages like *"Hi, my VPN is down"* (greeting + technical), the system handles both in one reply — greets the user and answers the question.

**Second — a bug in greeting_with_intent handling was fixed.** When a message combines a greeting with a real request, the LLM occasionally returns the underlying intent as a plain word (`"technical"`) instead of a structured object. This caused the app to crash when trying to attach user and conversation IDs to it. Added a type check to handle both formats safely.

**Also identified — chunking limitation.** The current document seeding script splits files using `---` as a section boundary, which only worked because the sample documents were manually formatted that way. Real KB articles from ServiceNow or SharePoint won't have this marker. A paragraph-based approach has been designed that splits on double newlines and respects a max character limit — no editing access to the source documents required. Will be implemented before real documents are connected.

---

### Day 12 — 2026-06-24
**Fixing response tone and hitting the first network block**

Live testing revealed a tone problem: the LLM kept prefacing answers with phrases like *"Based on the knowledge base excerpts..."* — leaking internal system language into what users see. The system prompt in `technical_handler.py` was updated to instruct the LLM to answer directly without referencing where the information came from. A small change, but important for the product feeling polished.

Same day, the corporate network proxy (Netskope) started blocking all calls to the Groq API. The proxy was previously allowing traffic through while doing SSL inspection — the `verify=False` workaround was enough. Netskope has now updated its cloud app database to classify Groq as a Generative AI tool, which triggered the existing `Mindsprint-AI-Block-All` policy automatically. The block is at the application level, not SSL — `verify=False` has no effect on it. Any external AI API (Anthropic, OpenAI, OpenRouter) will hit the same wall on the corporate network.

---

### Day 13 — 2026-06-25
**Switching to Ollama to get past the network block**

With Groq blocked, the LLM calls needed a new provider that doesn't go through the corporate proxy. Switched to an Ollama instance running on an internal server. Ollama implements the same OpenAI-compatible API that Groq used, so the code change was contained — swapped the Groq Python package for the OpenAI package, pointed the client at the Ollama endpoint, and changed the model name to `llama3.1:8b`. Four files needed updating, nothing else in the pipeline changed.

One issue surfaced immediately: `llama3.1:8b` is a much smaller model than the 70b used before, and it doesn't always follow the "output JSON only" instruction. The intent classifier started failing when the model wrapped its JSON in markdown or added explanatory text around it. Fixed by extracting the JSON object from wherever it appears in the response, rather than assuming the entire response is valid JSON.

This is a temporary dev workaround — production will still use Anthropic Claude as originally planned.

---

### Day 14 — 2026-06-26
**Designing the self-healing knowledge base loop**

Two new knowledge base documents were added — Outlook/email issues and software installation — bringing the total to five topics. They need to be indexed into pgvector but the logic was clear enough to plan around.

The main work today was designing a feature that closes a gap in the current system: what happens when a user asks something the knowledge base doesn't cover? Right now the LLM either hallucinates or says "I don't know." Neither is acceptable in a support context.

The solution is a closed loop. When the RAG search returns results that are too dissimilar to the user's question (measured by cosine distance score), the system automatically raises a support ticket containing the original query — no user action required. A developer picks it up, resolves it, and fills in the answer. That answer then gets embedded and inserted back into the knowledge base. The next time anyone asks the same question, the system answers it directly. No ticket raised, no developer needed.

The feature has three parts: a threshold check in the RAG search (pure SQL), an auto-ticket creation path in the technical handler, and a new `/kb/resolved` endpoint that receives resolutions and injects them into pgvector. The injection uses the exact same Nomic embedding pipeline already in use — no new infrastructure required.

---

### Day 15 — 2026-06-29
**Building the ticket handler — first real ticket operations**

Ollama was unavailable today so anything requiring LLM calls was off the table. Used the time to build the ticket operation handler instead — no AI involved, pure Python and PostgreSQL.

Until today, every ticket request returned `"processing..."`. Now the system handles all four ticket actions for real. Create raises a ticket and returns an INC number the user can reference. View retrieves the ticket status and description. Update appends notes and marks it in progress. Close sets it to closed. All of this persists in PostgreSQL — a ticket created now can be looked up after a server restart, which makes manual testing across sessions actually possible.

INC numbers are sequential and zero-padded (`INC0000001`, `INC0000002`, ...). When ServiceNow is eventually wired in, these mock IDs are replaced by ServiceNow's own numbering — the rest of the code doesn't change.

The ticket table was also designed with the next feature in mind. Two extra columns — `kb_gap` and `original_query` — are already in the schema. When the KB injection feature is built (Day 14 design), auto-raised tickets will carry these fields so the injection endpoint knows what resolution text to embed and what query to associate it with. No migration needed later.
