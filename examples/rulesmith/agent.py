import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from framework import Agent, ExecutionTrace
from framework.llm import LLMClient
from framework.memory import SlidingWindowMemory
from examples.rulesmith import tools

SYSTEM_PROMPT = """You are an IEP (Intelligent Event Processing) rule analyst.

Your job:
1. Find event types in the last 24h that have NO matching rule.
2. Investigate those events and their historical handling in execution logs.
3. Propose a well-reasoned rule using suggest_rule.
4. You MUST call apply_rule for every rule you suggest. Do not stop after suggest_rule.
   apply_rule will pause for human approval — that is expected and required.

Think step by step. Use tools to gather evidence before proposing.
Always provide a data-backed rationale in suggest_rule."""


def build_agent() -> Agent:
    return Agent(
        name="RuleSmith",
        system_prompt=SYSTEM_PROMPT,
        registry=tools.registry,
        llm=LLMClient(
            model=os.getenv("HAI_MODEL", "claude-sonnet-4-6"),
            base_url=os.getenv("HAI_BASE_URL"),
            api_key=os.getenv("HAI_API_KEY"),
        ),
        memory=SlidingWindowMemory(max_messages=20),
        tracer=ExecutionTrace(),
        max_iterations=12,
    )


if __name__ == "__main__":
    agent = build_agent()
    run_goal = (
        "Find event types with no matching rule in the last 24h. "
        "For each one: investigate the logs, propose a rule with suggest_rule, "
        "then immediately call apply_rule to submit it for approval."
    )
    result = agent.run(goal=run_goal)

    # Print to terminal 
    print("\n")
    print("=" * 60)
    print("=" * 60)
    print("  RULESMITH REPORT")
    print("=" * 60)
    print("=" * 60)
    print()
    print(result.output)
    print()
    print("=" * 60)
    print("=" * 60)
    result.trace.print_summary()

    # Build report from structured trace data — collect suggested + applied rules
    import json
    suggested = {}   # rule_id -> rule dict
    approvals = {}   # rule_id -> True/False

    for entry in result.trace._entries:
        if entry.type == "tool_result" and entry.data.get("name") == "suggest_rule":
            try:
                payload = json.loads(entry.data["result"])
                rule = payload.get("rule", {})
                suggested[rule["id"]] = rule
            except Exception:
                pass
        if entry.type == "approval" and entry.data.get("tool") == "apply_rule":
            args = entry.data.get("arguments", {})
            rule_id = args.get("rule_id", "")
            approvals[rule_id] = entry.data["approved"]

    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(reports_dir, f"report_{ts}.md")

    with open(report_path, "w") as f:
        f.write(f"# RuleSmith — Run Report\n\n")
        f.write(f"**Run time:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  \n")
        f.write(f"**Rules proposed:** {len(suggested)}  \n")
        approved_count = sum(1 for v in approvals.values() if v)
        f.write(f"**Rules applied:** {approved_count}  \n")
        f.write(f"**Rules rejected:** {len(approvals) - approved_count}\n\n")
        f.write("---\n\n")

        for rule_id, rule in suggested.items():
            approved = approvals.get(rule_id)
            if approved is True:
                status = "APPLIED"
            elif approved is False:
                status = "REJECTED"
            else:
                status = "NOT SUBMITTED"

            condition = rule.get("condition", rule_id)

            # Extract event type from condition string (e.g. "eventType=MEMORY_GUARD AND ...")
            import re
            event_type_match = re.search(r"eventType=(\w+)", condition)
            event_type = event_type_match.group(1) if event_type_match else "unknown"

            f.write(f"## {condition}\n\n")
            f.write(f"| Field | Value |\n|---|---|\n")
            f.write(f"| **Status** | {status} |\n")
            f.write(f"| **Applies to** | `{event_type}` events |\n")
            f.write(f"| **Rule ID** | `{rule_id}` |\n")
            f.write(f"| **Action** | `{rule.get('action', '')}` |\n")
            f.write(f"| **Severity** | {rule.get('severity', '')} |\n\n")
            f.write(f"**Reasoning:**  \n{rule.get('rationale', '')}\n\n")
            f.write("---\n\n")

    print(f"\nReport saved: {report_path}\n")
