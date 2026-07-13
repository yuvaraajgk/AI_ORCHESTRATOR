import os
os.environ["HF_HUB_OFFLINE"] = "1"

import psycopg2
from dotenv import load_dotenv
from rag import insert_document

load_dotenv()

DOCS_DIR = os.path.join(os.path.dirname(__file__), "sample_docs")

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
    conn.commit()

    for chunk in chunks:
        insert_document(source, chunk)

    print(f"  {filename} -> {len(chunks)} chunks")

cur.close()
conn.close()

print("Seeding complete.")
