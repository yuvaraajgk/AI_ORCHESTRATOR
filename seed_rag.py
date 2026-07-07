import os
os.environ["HF_HUB_OFFLINE"] = "1"

import psycopg2
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

DOCS_DIR = os.path.join(os.path.dirname(__file__), "sample_docs")
model = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)

conn = psycopg2.connect(os.getenv("RAG_DATABASE_URL"))
cur = conn.cursor()

for filename in sorted(os.listdir(DOCS_DIR)):
    if not filename.endswith(".txt"):
        continue

    source = filename.replace(".txt", "")

    with open(os.path.join(DOCS_DIR, filename), encoding="utf-8") as f:
        text = f.read()

    chunks = [c.strip() for c in text.split("---") if c.strip()]

    cur.execute("DELETE FROM documents WHERE source = %s", (source,))

    for chunk in chunks:
        embedding = model.encode(f"search_document: {chunk}").tolist()
        vector_str = "[" + ",".join(map(str, embedding)) + "]"
        cur.execute(
            "INSERT INTO documents (source, content, embedding) VALUES (%s, %s, %s::vector)",
            (source, chunk, vector_str)
        )

    print(f"  {filename} -> {len(chunks)} chunks")

conn.commit()
cur.close()
conn.close()

print("Seeding complete.")
