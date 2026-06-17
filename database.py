import os
import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()

_pool = SimpleConnectionPool(1, 10, os.getenv("DATABASE_URL"))


def _get_conn():
    return _pool.getconn()


def _put_conn(conn):
    _pool.putconn(conn)


def create_conversation(conversation_id: str, user_id: str):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO conversations (id, conversation_id, user_id, started_at, last_active_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (conversation_id) DO NOTHING
        """, (
            str(uuid4()),
            conversation_id,
            user_id,
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=30)
        ))
        conn.commit()
        cur.close()
    finally:
        _put_conn(conn)


def conversation_exists(conversation_id: str) -> bool:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM conversations WHERE conversation_id = %s", (conversation_id,))
        exists = cur.fetchone() is not None
        cur.close()
        return exists
    finally:
        _put_conn(conn)


def save_message(conversation_id: str, role: str, content: str, intent_category: str = None):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO messages (id, conversation_id, role, content, intent_category, created_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            str(uuid4()),
            conversation_id,
            role,
            content,
            intent_category,
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=30)
        ))
        cur.execute("""
            UPDATE conversations SET last_active_at = %s WHERE conversation_id = %s
        """, (datetime.now(timezone.utc), conversation_id))
        conn.commit()
        cur.close()
    finally:
        _put_conn(conn)


def get_conversations_by_user(user_id: str) -> list:
    conn = _get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT * FROM conversations
            WHERE user_id = %s AND expires_at > %s
        """, (user_id, datetime.now(timezone.utc)))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        return rows
    finally:
        _put_conn(conn)


def get_messages_by_conversation(conversation_id: str) -> list:
    conn = _get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT * FROM messages
            WHERE conversation_id = %s AND expires_at > %s
            ORDER BY created_at ASC
        """, (conversation_id, datetime.now(timezone.utc)))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        return rows
    finally:
        _put_conn(conn)
