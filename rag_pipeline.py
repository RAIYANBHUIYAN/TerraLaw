import os
import pickle

from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import InMemoryVectorStore

from terralaw_core import build_documents_from_text


PROCESSED_DATA_DIR = "Proessed_data"
VECTOR_DIR = "vectorstore"

os.makedirs(VECTOR_DIR, exist_ok=True)


def load_processed_data():
    docs = []

    if not os.path.exists(PROCESSED_DATA_DIR):
        print(f"Directory {PROCESSED_DATA_DIR} does not exist.")
        return docs

    for file_name in sorted(os.listdir(PROCESSED_DATA_DIR)):
        if not file_name.endswith("_cleaned.txt"):
            continue

        path = os.path.join(PROCESSED_DATA_DIR, file_name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                full_text = f.read()
            file_docs = build_documents_from_text(file_name, full_text)
            docs.extend(file_docs)
            print(f"Indexed {file_name}: {len(file_docs)} chunks")
        except Exception as exc:
            print(f"Error reading {file_name}: {exc}")

    return docs


docs = load_processed_data()
print("Total chunks:", len(docs))

embedder = SentenceTransformerEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

db = InMemoryVectorStore(embedding=embedder)
if docs:
    db.add_documents(docs)

with open(f"{VECTOR_DIR}/embeddings.pkl", "wb") as f:
    pickle.dump(db, f)

with open(f"{VECTOR_DIR}/documents.pkl", "wb") as f:
    pickle.dump(docs, f)

print("Vectorstore saved successfully!")
