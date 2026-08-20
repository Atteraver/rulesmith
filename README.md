# Agent Framework

A lightweight, reusable framework for building LLM agents: tool use, memory, and human-in-the-loop, with no orchestration library dependencies.

## Problem Statement

IEP (Intelligent Event Processing) systems route events to automated actions via rules. Rules age badly: new event types may emerge, operational patterns shift, and some events may fall through, operators silently by handling unmatched events by hand: raising alerts, restarting services. Those interventions never turning into rules.

Finding these gaps requires three things happening together: knowing which event types consistently go unmatched, understanding how the ops team has historically responded to those events, and translating that pattern into a correctly-scoped rule.
If done manually, this is a multi-step investigation across different data sources. Done wrong, it produces rules that are too broad (false positives) or too narrow (miss real incidents).


**RuleSmith solves this by acting as an analyst agent.** It is given a goal — *find events with no matching rule in the last 24 hours and suggest rules for them* — and it autonomously gathers the evidence, reasons over it, proposes a rule with a data-backed rationale, and then waits for human approval before writing anything to the system. The operator reviews one clearly-reasoned proposal rather than doing the investigation themselves.

---

## Demo

[Watch the 5-minute demo](https://sap-my.sharepoint.com/:v:/p/ahad_abbas_rizvi/IQD1HrH5U_rgSb9ga9K4JZbNAUW_lsmCOSAakXfSIryObYY?e=5l1MV4)

---

## What it does

The framework gives you a **free ReAct loop**: the LLM decides which tools to call, how many times, and in what order. You define tools with a decorator, hand them to an `Agent`, and call `agent.run(goal)`.

---

## 5 Capabilities

|   | Capability | Where |
|---|-----------|-------|
| 1 | **Tool Registry** — `@registry.tool` decorator turns any Python function into a callable tool with an auto-generated OpenAI schema | `framework/tool.py` |
| 2 | **ReAct Loop** — free, non-deterministic loop: LLM calls tools until it has enough to answer | `framework/agent.py` |
| 3 | **Short-Term Memory** — `SlidingWindowMemory` keeps the last N messages; system prompt always prepended | `framework/memory.py` |
| 4 | **Human Approval Gate** — `require_human_approval=True` on a tool pauses execution and prompts `[y/n]` before the tool fires | `framework/tool.py` |
| 5 | **Execution Trace** — every LLM decision, tool call, result, approval, and error logged with timestamps | `framework/tracer.py` |

---

## Setup

```bash
cd agent-framework
pip install -r requirements.txt

export HAI_BASE_URL=https://<your-hai-proxy-host>/v1
export HAI_API_KEY=<your-key>
export HAI_MODEL=claude-sonnet-4-6   # optional, this is the default
```

---

## Run the example agent

```bash
python -m examples.rulesmith.agent
```

The **RuleSmith** agent finds gaps in an IEP (Intelligent Event Processing) alert ruleset:

1. Fetches recent events and identifies event types with no matching alert rule
2. Digs into execution logs to understand how ops handled those events historically
3. Proposes new rules using `suggest_rule` (backed by data from steps 1–2)
4. For each proposed rule, **pauses and asks you to approve** before writing it to the system
5. Prints a full execution trace showing every decision the agent made

**What the approval prompt looks like:**

```
───────────────────────────────────────────────────────
  APPROVAL REQUIRED
───────────────────────────────────────────────────────
  The agent wants to call:  apply_rule
  Description: Apply a previously suggested rule to the IEP system by rule_id.

  What will happen:
    A new rule will be permanently added to the system.

  Rule ID:    rule-5fab50
  Condition:  eventType=MEMORY_GUARD AND memoryUsage >= 80 AND memoryUsage < 90
  Action:     CREATE_ALERT
  Severity:   MEDIUM
  Rationale:  9 MEMORY_GUARD events in the last 24h had no matching rule.
              Execution logs show repeated manual alert raises at 80–93%.
───────────────────────────────────────────────────────
  Approve this action? [y/n]:
```

Type `y` to apply the rule or `n` to skip it. The agent handles either response and continues.

---

## What one run looks like

A scripted pipeline hard-codes the call sequence: `get_recent_events → get_execution_logs → suggest_rule`. The ReAct loop has no prescribed order — the only exit condition is:

```python
if not tool_calls:
    return AgentResult(output=thought, trace=self._tracer)
```

Everything before that line is the LLM deciding what evidence it still needs. The trace below is from an actual run:

```
[01] get_existing_rules + get_recent_events(24h)   → 0 unmatched events                        [tool registry]
[06] get_recent_events(48h)                        → LLM widened the window — no code told it to  [ReAct loop]
[09] get_execution_logs ×2 + get_events_by_type ×2 → history + threshold data, 4 parallel calls  [ReAct loop]
[18] suggest_rule ×2                               → two rules staged, nothing written yet       [memory]
[23] apply_rule ×2                                 → MEMORY_GUARD: approved / SWAP_USAGE: rejected  [approval gate]
     30-entry trace printed                        → every decision, call, result timestamped    [execution trace]
```

Step [06] is the tell. The 24h window returned zero unmatched events. No code prescribed "try 48h if empty" — the LLM reasoned the window was too narrow and widened it. A scripted pipeline cannot do this; it would have exited with "nothing to do."

Step [23] shows the gate working on a real decision: `RESTART_SERVICE` on a CRITICAL event was rejected. The agent received `{"status": "rejected"}`, handled it gracefully, and produced a report that explained why the rejection might make sense — without crashing or retrying.

---

## Build your own agent

### 1. Define tools

```python
# my_agent/tools.py
from framework import ToolRegistry

registry = ToolRegistry()

@registry.tool(description="Look up a customer by ID.")
def get_customer(customer_id: str) -> dict:
    return {"id": customer_id, "name": "Alice", "tier": "premium"}

@registry.tool(description="Send a refund. Requires human approval.", require_human_approval=True)
def send_refund(customer_id: str, amount: float) -> dict:
    return {"status": "refunded", "customer_id": customer_id, "amount": amount}
```

### 2. Create and run the agent

```python
# my_agent/agent.py
import os
from framework import Agent
from framework.llm import LLMClient
from framework.memory import SlidingWindowMemory
from framework.tracer import ExecutionTrace
from my_agent import tools

agent = Agent(
    name="RefundAgent",
    system_prompt="You process customer refund requests. Always verify the customer exists first.",
    registry=tools.registry,
    llm=LLMClient(),
    memory=SlidingWindowMemory(max_messages=20),
    tracer=ExecutionTrace(),
)

result = agent.run("Process a refund of $29.99 for customer ID cust-42")
print(result.output)
result.trace.print_summary()
```

---

## Project structure

```
agent-framework/
├── framework/
│   ├── __init__.py       # Public API
│   ├── agent.py          # Agent class + ReAct loop
│   ├── tool.py           # @tool decorator, ToolRegistry, approval gate
│   ├── memory.py         # SlidingWindowMemory
│   ├── tracer.py         # ExecutionTrace
│   └── llm.py            # LLM client (OpenAI SDK → HAI proxy)
├── examples/
│   └── rulesmith/
│       ├── agent.py      # Wires up and runs RuleSmith
│       ├── tools.py      # 6 tools
│       └── mock_data.py  # Offline sample data (no external deps)
├── README.md
├── ARCHITECTURE.md
└── requirements.txt
```

---

## LLM backend

The framework uses the OpenAI SDK pointed at the HAI proxy (`HAI_BASE_URL`). Any OpenAI-compatible endpoint works. To swap to direct Anthropic, change `base_url` to `https://api.anthropic.com/v1` and update `HAI_API_KEY`.

---

## Coding agent used

**Claude Code** (`claude-sonnet-4-6`) via the Claude Code CLI.
