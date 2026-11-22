import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv()

from examples.rulesmith.retriever import search

TEST_CASES = [
    {
        "question": "What is the naming convention for a high-severity memory rule?",
        "ground_truth": "HIGH_MEMORY_GUARD_THRESHOLD",
    },
    {
        "question": "What action should be used for SWAP_USAGE events?",
        "ground_truth": "PAGE_ONCALL",
    },
    {
        "question": "What severity level is assigned to SWAP_USAGE events in the event taxonomy?",
        "ground_truth": "HIGH",
    },
    {
        "question": "What is the correct action for a MEMORY_GUARD event?",
        "ground_truth": "CREATE_ALERT",
    },
    {
        "question": "What component token is used for memory-related rules?",
        "ground_truth": "MEMORY",
    },
    {
        "question": "When should AUTO_RESTART be avoided?",
        "ground_truth": "For memory events without approval",
    },
    {
        "question": "What is the naming format for rule conditions?",
        "ground_truth": "<SEVERITY>_<COMPONENT>_<CONDITION>",
    },
    {
        "question": "Which event types in the taxonomy have no existing rule?",
        "ground_truth": "MEMORY_GUARD, SWAP_USAGE",
    },
]


def _build_ragas_dataset(results: list[dict]) -> "Dataset":
    from datasets import Dataset

    rows = {
        "question": [],
        "contexts": [],
        "ground_truth": [],
    }
    for r in results:
        rows["question"].append(r["question"])
        rows["contexts"].append([c["text"] for c in r["retrieved"]])
        rows["ground_truth"].append(r["ground_truth"])
    return Dataset.from_dict(rows)


def _build_llm():
    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper

    llm = ChatOpenAI(
        model=os.getenv("HAI_MODEL", "claude-sonnet-4-6"),
        base_url=os.getenv("HAI_BASE_URL"),
        api_key=os.getenv("HAI_API_KEY"),
    )
    return LangchainLLMWrapper(llm)


def run_eval():
    print("Retrieving context for each test case ...")
    results = []
    for tc in TEST_CASES:
        retrieved = search(tc["question"], top_k=3)
        results.append({
            "question": tc["question"],
            "ground_truth": tc["ground_truth"],
            "retrieved": retrieved,
        })

    print("Building RAGAS dataset ...")
    dataset = _build_ragas_dataset(results)

    print("Running ContextPrecision (requires LLM judge) ...")
    from ragas import evaluate
    from ragas.metrics import ContextPrecision, ContextEntityRecall

    llm = _build_llm()
    score_result = evaluate(
        dataset,
        metrics=[ContextPrecision(), ContextEntityRecall()],
        llm=llm,
    )

    scores = score_result.to_pandas()

    print(f"\n{'='*60}")
    print(f"  RAGAS EVALUATION RESULTS  ({len(TEST_CASES)} test cases)")
    print(f"{'='*60}")
    print(f"  {'Question':<52} {'CP':>6} {'CER':>6}")
    print(f"  {'-'*52} {'-'*6} {'-'*6}")
    for _, row in scores.iterrows():
        q = row["question"][:50] + ".." if len(row["question"]) > 50 else row["question"]
        cp = row.get("context_precision", float("nan"))
        cer = row.get("context_entity_recall", float("nan"))
        print(f"  {q:<52} {cp:>6.3f} {cer:>6.3f}")

    mean_cp = scores["context_precision"].mean()
    mean_cer = scores["context_entity_recall"].mean()
    print(f"  {'-'*52} {'-'*6} {'-'*6}")
    print(f"  {'MEAN':<52} {mean_cp:>6.3f} {mean_cer:>6.3f}")
    print(f"{'='*60}\n")

    # Save report
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"eval_rag_{ts}.json"

    report = {
        "run_time": datetime.now(timezone.utc).isoformat(),
        "test_cases": len(TEST_CASES),
        "mean_context_precision": round(mean_cp, 4),
        "mean_context_entity_recall": round(mean_cer, 4),
        "results": [
            {
                "question": row["question"],
                "ground_truth": results[i]["ground_truth"],
                "context_precision": round(row["context_precision"], 4),
                "context_entity_recall": round(row["context_entity_recall"], 4),
                "retrieved_sources": [c["source"] for c in results[i]["retrieved"]],
            }
            for i, (_, row) in enumerate(scores.iterrows())
        ],
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report saved: {report_path}\n")

    return mean_cp, mean_cer


if __name__ == "__main__":
    run_eval()
