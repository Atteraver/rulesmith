import json
from pathlib import Path

import hnswlib
import numpy as np

_INDEX_DIR = Path(__file__).parent / "policy_index"
_INDEX_PATH = _INDEX_DIR / "index.bin"
_CHUNKS_PATH = _INDEX_DIR / "chunks.json"

_index = None
_chunks = None
_embed_fn = None


def chunk_docs(policy_dir: Path) -> list[dict]:
    window = 150
    overlap = 30
    result = []
    chunk_id = 0
    for md_file in sorted(policy_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        words = text.split()
        step = window - overlap
        for start in range(0, max(1, len(words) - overlap), step):
            chunk_words = words[start:start + window]
            if not chunk_words:
                break
            result.append({
                "text": " ".join(chunk_words),
                "source": md_file.name,
                "chunk_id": chunk_id,
            })
            chunk_id += 1
            if start + window >= len(words):
                break
    return result


def build_embed_fn():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed(texts: list[str]) -> np.ndarray:
        return model.encode(texts, normalize_embeddings=True)

    return embed


def build_index(chunks: list[dict], embed_fn) -> hnswlib.Index:
    texts = [c["text"] for c in chunks]
    vectors = embed_fn(texts)
    dim = vectors.shape[1]
    index = hnswlib.Index(space="cosine", dim=dim)
    index.init_index(max_elements=len(chunks), M=16, ef_construction=200)
    index.set_ef(50)
    index.add_items(vectors, list(range(len(chunks))))
    return index


def save_index(index: hnswlib.Index, chunks: list[dict]):
    _INDEX_DIR.mkdir(parents=True, exist_ok=True)
    index.save_index(str(_INDEX_PATH))
    _CHUNKS_PATH.write_text(json.dumps(chunks, indent=2), encoding="utf-8")


def load_index() -> tuple[hnswlib.Index, list[dict]]:
    if not _INDEX_PATH.exists():
        raise RuntimeError(
            "Policy index not found. Run: python -m examples.rulesmith.ingest"
        )
    chunks = json.loads(_CHUNKS_PATH.read_text(encoding="utf-8"))
    dim = 384
    index = hnswlib.Index(space="cosine", dim=dim)
    index.load_index(str(_INDEX_PATH), max_elements=len(chunks))
    index.set_ef(50)
    return index, chunks


def _ensure_loaded():
    global _index, _chunks, _embed_fn
    if _index is None:
        _index, _chunks = load_index()
    if _embed_fn is None:
        _embed_fn = build_embed_fn()


def search(query: str, top_k: int = 3) -> list[dict]:
    _ensure_loaded()
    query_vec = _embed_fn([query])
    labels, distances = _index.knn_query(query_vec, k=min(top_k, len(_chunks)))
    results = []
    for label, distance in zip(labels[0], distances[0]):
        chunk = _chunks[label]
        results.append({
            "text": chunk["text"],
            "source": chunk["source"],
            "score": round(float(1 - distance), 4),
        })
    return results
