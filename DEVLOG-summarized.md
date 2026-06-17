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
