"""
FIRST thing to run. Checks that your Gemini key works and that Bangla retrieval makes sense.
    python scripts/test_embedding.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.embeddings import get_embedder


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))  # vectors are already normalized


emb = get_embedder()
question = "পাসপোর্ট নবায়নে কী কী কাগজ লাগে?"
passages = [
    "পাসপোর্ট নবায়নের জন্য পুরাতন পাসপোর্ট, জাতীয় পরিচয়পত্র এবং ফি জমার রসিদ প্রয়োজন।",   # relevant
    "আয়কর রিটার্ন জমার শেষ তারিখ প্রতি বছর নভেম্বর মাসে নির্ধারিত হয়।",                    # different topic
    "ঢাকা থেকে সিলেট যাওয়ার জন্য বাস ও ট্রেন দুটোই পাওয়া যায়।",                            # unrelated
]

q = emb.embed_query(question)
docs = emb.embed_documents(passages)
print(f"\nvector size: {len(q)}   (should be {emb.dim})\n")
for text, vec in zip(passages, docs):
    print(f"score {cosine(q, vec):.3f}  ->  {text}")
print("\nExpected: the FIRST passage must have the highest score. If yes, Bangla embeddings work.")
