import os
os.environ["HF_HUB_OFFLINE"] = "1"

from psycopg2.pool import SimpleConnectionPool
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

model = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)
_pool = SimpleConnectionPool(1, 5, os.getenv("RAG_DATABASE_URL"))


def search(query: str, top_k: int = 5) -> tuple[list[str], list[float]]:
    embedding = model.encode(f"search_query: {query}").tolist()
    vector_str = "[" + ",".join(map(str, embedding)) + "]"
    conn = _pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT content, embedding <=> %s::vector AS score
            FROM documents
            ORDER BY score
            LIMIT %s
        """, (vector_str, top_k))
        rows = cur.fetchall()
        cur.close()
        chunks = [row[0] for row in rows]
        scores = [float(row[1]) for row in rows]
        return chunks, scores
    finally:
        _pool.putconn(conn)
