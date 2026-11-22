from pathlib import Path

from examples.rulesmith.retriever import chunk_docs, build_embed_fn, build_index, save_index, _INDEX_DIR

_POLICY_DIR = Path(__file__).parent / "policy_docs"


def main():
    print("Downloading embedding model 'all-MiniLM-L6-v2' (~90MB, one-time)...")
    embed_fn = build_embed_fn()

    print(f"Chunking policy docs from {_POLICY_DIR} ...")
    chunks = chunk_docs(_POLICY_DIR)
    print(f"  {len(chunks)} chunks from {len(list(_POLICY_DIR.glob('*.md')))} files")

    print("Building HNSW index ...")
    index = build_index(chunks, embed_fn)

    save_index(index, chunks)
    print(f"Index saved to {_INDEX_DIR}/")
    print(f"  index.bin + chunks.json written ({len(chunks)} chunks total)")


if __name__ == "__main__":
    main()
