# Plan: RAG + RAGAS on top of Rulesmith

## Context

Rulesmith is a ReAct-loop IEP analyst agent that finds unmatched alert events, investigates them via
structured tool calls, and proposes rules. Currently the agent has no access to written policy —
it cannot know that a rule for `MEMORY_GUARD` should be named `HIGH_MEMORY_GUARD_THRESHOLD` or that
the correct action for swap events is `PAGE_ONCALL`. This plan adds:

1. **A `search_policy_docs` tool** — semantic retrieval over 3 policy markdown files using an HNSW
   index (via `hnswlib`) and `sentence-transformers` embeddings.
2. **A RAGAS evaluation harness** — measures context precision and context entity recall of the
   new retrieval tool using the same HAI proxy as an LLM judge for `ContextPrecision`.

**Minimal disruption guarantee:** `framework/` (all 5 files) and `mock_data.py` are not modified.
Two files in `examples/rulesmith/` receive small additive changes: one sentence appended to
`SYSTEM_PROMPT` in `agent.py`, and one tool appended to `tools.py`. All other new code is in new files.

---

## Final File Tree (new files only)

```
rulesmith/
  requirements.txt                          ← add 5 packages
  examples/rulesmith/
    tools.py                                ← add search_policy_docs tool (10 lines at bottom)
    agent.py                                ← append 1 sentence to SYSTEM_PROMPT only
    policy_docs/
      rule-naming-conventions.md            ← new policy doc
      event-taxonomy.md                     ← new policy doc
      allowed-actions.md                    ← new policy doc
    retriever.py                            ← new: HNSW index + search
    ingest.py                               ← new: one-time ingestion script
    eval_rag.py                             ← new: RAGAS evaluation harness
    policy_index/                           ← created at ingest time (gitignored)
      index.bin
      chunks.json
```

---

## Step-by-Step Implementation

### Step 1 — Policy docs (3 markdown files)

**`policy_docs/rule-naming-conventions.md`**
- Naming format: `<SEVERITY>_<COMPONENT>_<CONDITION>`
- Severity levels: CRITICAL, HIGH, MEDIUM, LOW with definitions
- Component tokens: MEMORY, SWAP, CPU, DISK, NETWORK, DB, APP
- Condition tokens: THRESHOLD, SPIKE, GUARD, EXHAUSTED, PRESSURE, OVERFLOW
- Full examples table: `HIGH_MEMORY_GUARD_THRESHOLD`, `CRITICAL_SWAP_OVERFLOW`, `HIGH_CPU_SPIKE_THRESHOLD` etc.
- Anti-patterns to avoid

**`policy_docs/event-taxonomy.md`**
- Table of all known event types from mock_data.py
- Special section on the two *unmatched* types: `MEMORY_GUARD` and `SWAP_USAGE` with their
  typical threshold ranges and historical operator responses
- Event groupings: Resource events, Application events, Database events

**`policy_docs/allowed-actions.md`**
- Full table of valid action strings: `CREATE_ALERT`, `PAGE_ONCALL`, `AUTO_RESTART`, `LOG_ONLY`, `SCALE_UP`
- When each is appropriate (severity thresholds, event categories)
- Explicitly: `SWAP_USAGE` → `PAGE_ONCALL`; `MEMORY_GUARD` → `CREATE_ALERT`
- Anti-patterns (do not use `AUTO_RESTART` for memory events without approval)

---

### Step 2 — `retriever.py`

Responsibilities:
- `chunk_docs(policy_dir)` — reads every `.md` file, sliding window of 150 words / 30-word overlap,
  returns `[{text, source, chunk_id}]`
- `build_embed_fn()` — loads `sentence-transformers all-MiniLM-L6-v2` (384-dim); no fallback —
  `sentence-transformers` is a hard dependency in `requirements.txt`. The model is loaded lazily
  inside `_ensure_loaded()` so it is available both at ingest time and at query time (first search
  call incurs ~1s load; subsequent calls reuse the cached instance).
- `build_index(chunks, embed_fn)` — builds `hnswlib.Index(space='cosine', dim=384)` with
  `M=16, ef_construction=200, ef=50`
- `save_index(index, chunks)` / `load_index()` — persists `index.bin` + `chunks.json` to
  `policy_index/` relative to `retriever.py`'s own directory (`Path(__file__).parent / "policy_index"`);
  anchored to the file's location so it works regardless of the working directory the script is
  invoked from. `load_index()` catches `FileNotFoundError` and raises
  `RuntimeError("Policy index not found. Run: python -m examples.rulesmith.ingest")` with a clean
  message rather than a raw traceback
- `_ensure_loaded()` — lazy loader called inside `search()`; raises `RuntimeError("Policy index not found. Run: python -m examples.rulesmith.ingest")` if no index on disk
- `search(query, top_k=3)` — embeds query, calls `index.knn_query`, returns
  `[{text, source, score}]` (score = `1 - distance`, range 0–1)

HNSW parameters:
- `M=16` — number of connections per node (memory vs recall tradeoff)
- `ef_construction=200` — build-time accuracy (higher = slower build, better recall)
- `ef=50` — query-time accuracy (higher = slower query, better recall)
- `space='cosine'` — cosine similarity (hnswlib normalizes internally)

---

### Step 3 — `ingest.py`

One-time script run before the agent:
```
python -m examples.rulesmith.ingest
```
Reads policy docs → chunks → embeds → saves HNSW index. Idempotent (safe to re-run if docs change).

**Model download notice:** `ingest.py` prints the following before loading the embedding model so
developers know why it pauses (~90MB download from HuggingFace Hub on first run):
```
Downloading embedding model 'all-MiniLM-L6-v2' (~90MB, one-time)...
```

**Lazy error on missing index:** `retriever.py`'s `_ensure_loaded()` raises
`RuntimeError("Policy index not found. Run: python -m examples.rulesmith.ingest")` if
`policy_index/index.bin` does not exist. This triggers only when `search_policy_docs` is first
called — the existing 6 tools are unaffected and the agent starts normally without the index.
No startup check is added to `agent.py`.

---

### Step 4 — Add `search_policy_docs` to `tools.py`

Appended at the bottom of `examples/rulesmith/tools.py` after `apply_rule`:

```python
@registry.tool(
    description=(
        "Search IEP policy documents for rule naming conventions, event type guidance, "
        "or allowed action values. Use before suggest_rule to ensure the proposed rule "
        "follows team standards. top_k defaults to 3 (number of chunks returned)."
    )
)
def search_policy_docs(query: str, top_k: int = 3) -> list:
    from .retriever import search
    return search(query, top_k)
```

Auto-registers into the existing `registry` — no other lines in `tools.py` change.

---

### Step 5 — System prompt update in `agent.py`

Append one sentence to `SYSTEM_PROMPT`:
> `Before calling suggest_rule, use search_policy_docs to check naming conventions and the correct action for the event type you are proposing.`

No other change to `agent.py`.

---

### Step 6 — `eval_rag.py` (RAGAS harness)

Evaluates the `search_policy_docs` retrieval tool in isolation — not the full agent run.

**8 test cases:**

| # | Question | Ground truth |
|---|---|---|
| 1 | What is the naming convention for a high-severity memory rule? | `HIGH_MEMORY_GUARD_THRESHOLD` |
| 2 | What action should be used for SWAP_USAGE events? | `PAGE_ONCALL` |
| 3 | What severity level is assigned to SWAP_USAGE events in the event taxonomy? | HIGH |
| 4 | What is the correct action for a MEMORY_GUARD event? | `CREATE_ALERT` |
| 5 | What component token is used for memory-related rules? | MEMORY |
| 6 | When should AUTO_RESTART be avoided? | For memory events without approval |
| 7 | What is the naming format for rule conditions? | `<SEVERITY>_<COMPONENT>_<CONDITION>` |
| 8 | Which event types in the taxonomy have no existing rule? | MEMORY_GUARD, SWAP_USAGE |

**RAGAS metrics:**
- `ContextPrecision` — are retrieved chunks actually relevant to the question? Uses an LLM judge (`LangchainLLMWrapper`) — the HAI proxy is required for this metric.
- `ContextEntityRecall` — do chunks contain the key entities from the ground-truth answer? Entity overlap, no LLM judge needed.

> **Note:** `ContextRecall` and `Faithfulness` are excluded — both require an LLM to judge a generated
> answer against the retrieved context, making them generation metrics, not retrieval metrics.
> This harness evaluates retrieval quality only. To add faithfulness: wire a generation step
> (`answer = llm.chat([{"role":"user","content": question + context}])`), then pass it to RAGAS.

**LLM adapter for RAGAS:** `LangchainLLMWrapper` around `ChatOpenAI` pointed at `HAI_BASE_URL` —
same env vars already in the project (`HAI_BASE_URL`, `HAI_API_KEY`, `HAI_MODEL`).
`eval_rag.py` must call `load_dotenv()` at the top (same as `llm.py`) since it is a standalone
entry point and the env vars are not loaded automatically.

**Output:** printed table + saved to `examples/rulesmith/reports/eval_rag_<timestamp>.json`

---

### Step 7 — `requirements.txt` additions

```
openai>=1.30.0           # already present
hnswlib>=0.8.0           # HNSW vector index
sentence-transformers>=3.0.0  # embeddings (model downloaded from HuggingFace Hub at ingest time)
ragas>=0.2.0,<0.3.0      # evaluation framework (pinned — API changes between minor versions)
langchain-openai>=0.1.0  # RAGAS LLM adapter
```

---

### Step 8 — `.gitignore` (create)

```
examples/rulesmith/policy_index/
```
No `.gitignore` exists in the repo yet — this creates it. Binary HNSW index should not be committed — regenerated by `ingest.py`.

---

## File Modification Summary

| File | Type | Change |
|---|---|---|
| `requirements.txt` | Modified | Add 4 new packages |
| `examples/rulesmith/agent.py` | Modified | +1 sentence to SYSTEM_PROMPT |
| `examples/rulesmith/tools.py` | Modified | Add `search_policy_docs` tool (~10 lines at bottom) |
| `examples/rulesmith/policy_docs/rule-naming-conventions.md` | New | Policy content |
| `examples/rulesmith/policy_docs/event-taxonomy.md` | New | Policy content |
| `examples/rulesmith/policy_docs/allowed-actions.md` | New | Policy content |
| `examples/rulesmith/retriever.py` | New | HNSW index + search |
| `examples/rulesmith/ingest.py` | New | One-time ingestion script |
| `examples/rulesmith/eval_rag.py` | New | RAGAS harness |
| `.gitignore` | Created | Add `policy_index/` (file does not exist yet) |

**Zero changes to:** `framework/` (all 5 files), `examples/rulesmith/mock_data.py`

---

## Verification Steps

1. **Install deps:**
   ```bash
   cd /Users/I578085/Documents/GitHub/rulesmith
   .venv/bin/pip install hnswlib sentence-transformers ragas langchain-openai
   ```

2. **Ingest policy docs:**
   ```bash
   python -m examples.rulesmith.ingest
   # First run downloads embedding model (~90MB from HuggingFace Hub) — this is expected.
   # Expected output: "Chunked N chunks from policy_docs/ — Index saved to policy_index/"
   ```

3. **Smoke test retrieval:**
   ```python
   from examples.rulesmith.retriever import search
   print(search("naming convention for memory rule", top_k=3))
   # Expected: top result from rule-naming-conventions.md, score > 0.7
   ```

4. **Run the agent:**
   ```bash
   python -m examples.rulesmith.agent
   # Check trace: search_policy_docs appears before suggest_rule
   # Check proposed rule names conform to <SEVERITY>_<COMPONENT>_<CONDITION>
   ```

5. **Run RAGAS eval:**
   ```bash
   python -m examples.rulesmith.eval_rag
   # Target: context_precision > 0.80, context_entity_recall > 0.75
   ```

6. **Regression check:** running the agent without `policy_index/` present gives a clear
   `RuntimeError("Policy index not found. Run: python -m examples.rulesmith.ingest")` only if
   `search_policy_docs` is called — existing 6 tools are unaffected.
