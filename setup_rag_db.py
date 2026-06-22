import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("RAG_DATABASE_URL"))
cur = conn.cursor()

cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

cur.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id        SERIAL PRIMARY KEY,
        source    TEXT,
        content   TEXT,
        embedding vector(768)
    )
""")

conn.commit()
cur.close()
conn.close()

print("RAG database ready.")
