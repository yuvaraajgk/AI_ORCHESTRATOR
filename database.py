from datetime import datetime, timedelta
from uuid import uuid4

# ─── REAL SQL SETUP (uncomment when DB is available) ───────────────────────────
#
# import os
# from sqlalchemy import create_engine, text
# from sqlalchemy.orm import sessionmaker
#
# DATABASE_URL = os.getenv("DATABASE_URL")
# # SQL Server:   "mssql+pyodbc://user:pass@host/dbname?driver=ODBC+Driver+17+for+SQL+Server"
# # PostgreSQL:   "postgresql+psycopg2://user:pass@host/dbname"
#
# engine = create_engine(DATABASE_URL)
# SessionLocal = sessionmaker(bind=engine)
#
# SQL SCHEMA (run once on your DB):
#
# CREATE TABLE conversations (
#     id               VARCHAR(36)  PRIMARY KEY,
#     conversation_id  VARCHAR(100) UNIQUE NOT NULL,
#     user_id          VARCHAR(100) NOT NULL,
#     started_at       DATETIME     NOT NULL,
#     last_active_at   DATETIME     NOT NULL,
#     expires_at       DATETIME     NOT NULL
# );
#
# CREATE TABLE messages (
#     id               VARCHAR(36)  PRIMARY KEY,
#     conversation_id  VARCHAR(100) NOT NULL REFERENCES conversations(conversation_id),
#     role             VARCHAR(20)  NOT NULL,   -- 'user' or 'assistant'
#     content          TEXT         NOT NULL,
#     intent_category  VARCHAR(50),             -- 'greeting', 'technical', 'ticket_op' (user msgs only)
#     created_at       DATETIME     NOT NULL,
#     expires_at       DATETIME     NOT NULL
# );
#
# -- Auto-cleanup job (run as scheduled SQL job nightly):
# -- DELETE FROM messages      WHERE expires_at < GETDATE();
# -- DELETE FROM conversations WHERE expires_at < GETDATE();
#
# ───────────────────────────────────────────────────────────────────────────────


# ─── IN-MEMORY MOCK ────────────────────────────────────────────────────────────

_conversations: dict = {}   # conversation_id → conversation record
_messages: list     = []    # flat list of all messages


def create_conversation(conversation_id: str, user_id: str):
    # ── Real SQL ──────────────────────────────────────────────────────────────
    # db = SessionLocal()
    # db.execute(text("""
    #     INSERT INTO conversations (id, conversation_id, user_id, started_at, last_active_at, expires_at)
    #     VALUES (:id, :cid, :uid, :now, :now, :exp)
    # """), {"id": str(uuid4()), "cid": conversation_id, "uid": user_id,
    #        "now": datetime.utcnow(), "exp": datetime.utcnow() + timedelta(days=30)})
    # db.commit()
    # db.close()
    # ─────────────────────────────────────────────────────────────────────────

    _conversations[conversation_id] = {
        "id": str(uuid4()),
        "conversation_id": conversation_id,
        "user_id": user_id,
        "started_at": datetime.utcnow(),
        "last_active_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=30)
    }


def conversation_exists(conversation_id: str) -> bool:
    # ── Real SQL ──────────────────────────────────────────────────────────────
    # db = SessionLocal()
    # result = db.execute(text(
    #     "SELECT 1 FROM conversations WHERE conversation_id = :cid"
    # ), {"cid": conversation_id}).fetchone()
    # db.close()
    # return result is not None
    # ─────────────────────────────────────────────────────────────────────────

    return conversation_id in _conversations


def save_message(conversation_id: str, role: str, content: str, intent_category: str = None):
    # ── Real SQL ──────────────────────────────────────────────────────────────
    # db = SessionLocal()
    # db.execute(text("""
    #     INSERT INTO messages (id, conversation_id, role, content, intent_category, created_at, expires_at)
    #     VALUES (:id, :cid, :role, :content, :intent, :now, :exp)
    # """), {"id": str(uuid4()), "cid": conversation_id, "role": role,
    #        "content": content, "intent": intent_category,
    #        "now": datetime.utcnow(), "exp": datetime.utcnow() + timedelta(days=30)})
    # db.execute(text(
    #     "UPDATE conversations SET last_active_at = :now WHERE conversation_id = :cid"
    # ), {"now": datetime.utcnow(), "cid": conversation_id})
    # db.commit()
    # db.close()
    # ─────────────────────────────────────────────────────────────────────────

    _messages.append({
        "id": str(uuid4()),
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "intent_category": intent_category,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=30)
    })
    if conversation_id in _conversations:
        _conversations[conversation_id]["last_active_at"] = datetime.utcnow()


def get_conversations_by_user(user_id: str) -> list:
    # ── Real SQL ──────────────────────────────────────────────────────────────
    # db = SessionLocal()
    # rows = db.execute(text("""
    #     SELECT conversation_id, started_at, last_active_at
    #     FROM conversations
    #     WHERE user_id = :uid AND expires_at > :now
    #     ORDER BY last_active_at DESC
    # """), {"uid": user_id, "now": datetime.utcnow()}).fetchall()
    # db.close()
    # return [dict(r) for r in rows]
    # ─────────────────────────────────────────────────────────────────────────

    now = datetime.utcnow()
    return [
        c for c in _conversations.values()
        if c["user_id"] == user_id and c["expires_at"] > now
    ]


def get_messages_by_conversation(conversation_id: str) -> list:
    # ── Real SQL ──────────────────────────────────────────────────────────────
    # db = SessionLocal()
    # rows = db.execute(text("""
    #     SELECT role, content, intent_category, created_at
    #     FROM messages
    #     WHERE conversation_id = :cid AND expires_at > :now
    #     ORDER BY created_at ASC
    # """), {"cid": conversation_id, "now": datetime.utcnow()}).fetchall()
    # db.close()
    # return [dict(r) for r in rows]
    # ─────────────────────────────────────────────────────────────────────────

    now = datetime.utcnow()
    return [
        m for m in _messages
        if m["conversation_id"] == conversation_id and m["expires_at"] > now
    ]
