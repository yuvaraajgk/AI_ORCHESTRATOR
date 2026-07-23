import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id               VARCHAR(36)  PRIMARY KEY,
        conversation_id  VARCHAR(100) UNIQUE NOT NULL,
        user_id          VARCHAR(100) NOT NULL,
        started_at       TIMESTAMP    NOT NULL,
        last_active_at   TIMESTAMP    NOT NULL,
        expires_at       TIMESTAMP    NOT NULL
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id               VARCHAR(36)  PRIMARY KEY,
        conversation_id  VARCHAR(100) NOT NULL REFERENCES conversations(conversation_id),
        role             VARCHAR(20)  NOT NULL,
        content          TEXT         NOT NULL,
        intent_category  VARCHAR(50),
        created_at       TIMESTAMP    NOT NULL,
        expires_at       TIMESTAMP    NOT NULL
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id               VARCHAR(36)   PRIMARY KEY,
        ticket_id        VARCHAR(20)   UNIQUE NOT NULL,
        user_id          VARCHAR(100)  NOT NULL,
        conversation_id  VARCHAR(100)  NOT NULL,
        status           VARCHAR(20)   NOT NULL DEFAULT 'open',
        description      TEXT          NOT NULL,
        resolution       TEXT,
        kb_gap           BOOLEAN       NOT NULL DEFAULT FALSE,
        original_query   TEXT,
        created_at       TIMESTAMP     NOT NULL,
        updated_at       TIMESTAMP     NOT NULL
    )
""")

# real sequence, not COUNT(*) — the old scheme collided with existing IDs
# whenever a row was deleted. Seeded past the highest ID already in the table.
cur.execute("""
    SELECT COALESCE(MAX(CAST(SUBSTRING(ticket_id FROM 4) AS INTEGER)), 0) FROM tickets
""")
max_existing = cur.fetchone()[0]
cur.execute(f"CREATE SEQUENCE IF NOT EXISTS ticket_id_seq START WITH {max_existing + 1}")

conn.commit()
cur.close()
conn.close()

print("Tables created successfully.")
