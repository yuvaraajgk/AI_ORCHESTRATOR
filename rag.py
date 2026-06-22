import os
import httpx

_orig_init = httpx.Client.__init__
def _no_ssl_init(self, *args, **kwargs):
    kwargs.setdefault("verify", False)
    _orig_init(self, *args, **kwargs)
httpx.Client.__init__ = _no_ssl_init

from psycopg2.pool import SimpleConnectionPool
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

model = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)
_pool = SimpleConnectionPool(1, 5, os.getenv("RAG_DATABASE_URL"))


def search(query: str, top_k: int = 5) -> list[str]:
    embedding = model.encode(f"search_query: {query}").tolist()
    vector_str = "[" + ",".join(map(str, embedding)) + "]"
    conn = _pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT content FROM documents
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (vector_str, top_k))
        rows = cur.fetchall()
        cur.close()
        return [row[0] for row in rows]
    finally:
        _pool.putconn(conn)
