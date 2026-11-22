import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from framework import ToolRegistry
from . import mock_data

registry = ToolRegistry()

# Pending rules staged by suggest_rule, consumed by apply_rule
_pending_rules: dict[str, dict] = {}


@registry.tool(description="Get all existing rules with their conditions and actions.")
def get_existing_rules() -> list:
    return mock_data.RULES


@registry.tool(
    description=(
        "Get recent events and which rule matched (if any). "
        "Pass hours=24 to get last 24h, hours=48 for 48h."
    )
)
def get_recent_events(hours: int = 24) -> dict:
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    filtered = [
        e for e in mock_data.RECENT_EVENTS
        if datetime.fromisoformat(e["timestamp"]) >= cutoff
    ]
    unmatched = [e for e in filtered if e["matchedRule"] is None]
    unmatched_types = {}
    for e in unmatched:
        unmatched_types[e["type"]] = unmatched_types.get(e["type"], 0) + 1

    return {
        "total": len(filtered),
        "unmatched_count": len(unmatched),
        "unmatched_by_type": unmatched_types,
        "sample_unmatched": unmatched[:5],
    }


@registry.tool(
    description="Get execution logs for a specific event type showing historical outcomes (e.g. 'MEMORY_GUARD')."
)
def get_execution_logs(event_type: str) -> list:
    return [e for e in mock_data.EXECUTION_LOGS if e["eventType"] == event_type]


@registry.tool(
    description="Get all recent events filtered by type for deeper pattern analysis (e.g. 'MEMORY_GUARD')."
)
def get_events_by_type(event_type: str) -> list:
    return [e for e in mock_data.RECENT_EVENTS if e["type"] == event_type]


@registry.tool(
    description=(
        "Propose a new rule as structured JSON. Does NOT apply it — stores it as pending. "
        "Returns a rule_id that can be passed to apply_rule."
    )
)
def suggest_rule(condition: str, action: str, severity: str, rationale: str) -> dict:
    import uuid
    rule_id = f"rule-{uuid.uuid4().hex[:6]}"
    rule = {
        "id": rule_id,
        "condition": condition,
        "action": action,
        "severity": severity,
        "rationale": rationale,
        "status": "pending",
    }
    _pending_rules[rule_id] = rule
    return {"rule_id": rule_id, "rule": rule, "message": "Rule staged. Call apply_rule to activate."}


def _apply_rule_context(args: dict) -> str:
    rule_id = args.get("rule_id", "")
    rule = _pending_rules.get(rule_id)
    if not rule:
        return f"  Rule ID: {rule_id}  (not found in pending rules)"
    lines = [
        f"  What will happen:",
        f"    A new rule will be permanently added to the system.",
        f"",
        f"  Rule ID:    {rule['id']}",
        f"  Condition:  {rule['condition']}",
        f"  Action:     {rule['action']}",
        f"  Severity:   {rule['severity']}",
        f"  Rationale:  {rule['rationale']}",
    ]
    return "\n".join(lines)


@registry.tool(
    description="Apply a previously suggested rule to the system by rule_id. Requires human approval.",
    require_human_approval=True,
    approval_context_fn=_apply_rule_context,
)
def apply_rule(rule_id: str) -> dict:
    rule = _pending_rules.get(rule_id)
    if rule is None:
        return {"error": f"No pending rule with id '{rule_id}'. Call suggest_rule first."}

    rule["status"] = "active"
    mock_data.RULES.append({
        "id": rule["id"],
        "condition": rule["condition"],
        "action": rule["action"],
        "severity": rule["severity"],
    })
    del _pending_rules[rule_id]
    return {"status": "applied", "rule": rule, "total_rules": len(mock_data.RULES)}


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
