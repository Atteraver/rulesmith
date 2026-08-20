# Architecture 

## Problem Statement

IEP (Intelligent Event Processing) systems route events to automated actions via rules. Rules age badly: new event types may emerge, operational patterns shift, and some events may fall through, operators silently by handling unmatched events by hand: raising alerts, restarting services. Those interventions never turning into rules.

Finding these gaps requires three things happening together: knowing which event types consistently go unmatched, understanding how the ops team has historically responded to those events, and translating that pattern into a correctly-scoped rule. 
If done manually, this is a multi-step investigation across different data sources. Done wrong, it produces rules that are too broad (false positives) or too narrow (miss real incidents).


**RuleSmith solves this by acting as an analyst agent.** It is given a goal — *find events with no matching rule in the last 24 hours and suggest rules for them* — and it autonomously gathers the evidence, reasons over it, proposes a rule with a data-backed rationale, and then waits for human approval before writing anything to the system. The operator reviews one clearly-reasoned proposal rather than doing the investigation themselves.

---

## RuleSmith Tools

The example agent registers six tools, each mapped to one step of the investigation:

| Tool | Purpose | Approval required |
|------|---------|-------------------|
| `get_recent_events(hours)` | Returns event counts for the last N hours, split by matched vs unmatched rule | No |
| `get_existing_rules()` | Returns the full current ruleset with conditions, actions, and severities | No |
| `get_execution_logs(event_type)` | Returns historical operator interventions for a specific event type (manual alerts, restarts, etc.) | No |
| `get_events_by_type(event_type)` | Returns raw events filtered by type for deeper pattern analysis (e.g. threshold distribution) | No |
| `suggest_rule(condition, action, severity, rationale)` | Stores a proposed rule in memory and returns a `rule_id`; does not write to the system | No |
| `apply_rule(rule_id)` | Writes a previously suggested rule to the IEP system permanently | **Yes — `[y/n]` gate** |

The read-only tools (`get_*`) are always safe to call — the LLM may call them in any order it chooses. `suggest_rule` is a staging step: the rule exists only in memory until `apply_rule` is called. `apply_rule` is the only tool that changes system state, and it is the only one that requires human approval. This split ensures the agent can propose rules freely without any risk of accidental writes.

---

## Components

```
┌─────────────────────────────────────────────────────────┐
│                        Agent                            │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  LLMClient  │  │ToolRegistry  │  │SlidingWindow  │  │
│  │             │  │              │  │   Memory      │  │
│  │ OpenAI SDK  │  │ @tool deco-  │  │               │  │
│  │ → HAI proxy │  │ rator + call │  │ last N msgs   │  │
│  └─────────────┘  │ + approval   │  │ + system msg  │  │
│                   │ gate         │  └───────────────┘  │
│                   └──────────────┘                      │
│  ┌──────────────────────────────┐                       │
│  │       ExecutionTrace         │                       │
│  │  step / type / ts / data     │                       │
│  └──────────────────────────────┘                       │
└─────────────────────────────────────────────────────────┘
```

### Component responsibilities

| Component | File | Role |
|-----------|------|------|
| `Agent` | `agent.py` | Owns the ReAct loop; wires all other components together |
| `LLMClient` | `llm.py` | Single method `chat(messages, tools)` — sends to HAI proxy, returns raw message |
| `ToolRegistry` | `tool.py` | Stores tool definitions; generates OpenAI schemas; executes tools; runs approval gate |
| `SlidingWindowMemory` | `memory.py` | Keeps last N messages; always prepends system prompt |
| `ExecutionTrace` | `tracer.py` | Append-only log of every decision, call, result, approval, and error |

---

## Data Flow

One full iteration of the ReAct loop:

```
User goal
    │
    ▼
memory.add(role="user", content=goal)
    │
    ▼
┌───────────────────────────────────────────────────────┐
│                     REACT LOOP                        │
│                                                       │
│  memory.messages() ──► LLMClient.chat()               │
│  registry.to_openai_schema() ──►                      │
│                                                       │
│         LLM response                                  │
│              │                                        │
│    ┌─────────┴──────────┐                             │
│    │                    │                             │
│  tool_calls           text only                       │
│    │                    │                             │
│    ▼                    ▼                             │
│  for each call:      EXIT LOOP                        │
│    │                                                  │
│    ├─ require_human_approval?                         │
│    │     └─ print context + [y/n]                     │
│    │          ├─ n → return rejection payload         │
│    │          └─ y → continue                         │
│    │                                                  │
│    ├─ registry.call(name, args) → result              │
│    ├─ memory.add(role="tool", content=result)         │
│    └─ trace.record(tool_call + tool_result)           │
│                                                       │
│  [loop back — LLM sees tool results, decides next]    │
└───────────────────────────────────────────────────────┘
    │
    ▼
AgentResult(output=text, trace=ExecutionTrace)
```

---

## Framework Design

**ReAct over phase-based pipelines.**
A phase-based agent has a fixed call sequence baked in — gather data, then analyse, then propose. The LLM is just filling slots. A scripted version of RuleSmith would look like `get_recent_events → get_execution_logs → suggest_rule`, hardcoded in that order. A free ReAct loop has no prescribed order: after every tool result the LLM decides what to call next, or whether it's done. The only exit condition is `if not tool_calls: return` (`agent.py:55-56`); everything before that line is the LLM reasoning over what it still needs. In RuleSmith this means the LLM might call `get_events_by_type` before `suggest_rule`, or skip it entirely — that path isn't scripted anywhere in the code.

In practice this matters: in a real run, `get_recent_events(24)` returned zero unmatched events. No code said "try 48h if empty." The LLM saw the result, inferred the window was too narrow, and called `get_recent_events(48)` on the next iteration — finding 40 unmatched events that a scripted pipeline would have missed entirely. A fixed sequence (`get_recent_events → get_execution_logs → suggest_rule`) cannot adapt like this; it would have exited with "nothing to do."

**Approval gate on the tool, not the agent.**
`apply_rule` is decorated with `require_human_approval=True`. When `registry.call()` hits that flag, it prints the tool name, description, and an optional `approval_context_fn` output (in RuleSmith's case: the full rule details), then blocks on `input()`. The LLM has no visibility into this — it called the tool normally and simply doesn't receive a result until the operator responds. A rejection returns a JSON payload `{"status": "rejected"}` rather than raising, so the agent can handle it gracefully and continue. Putting this on the tool rather than the agent means any agent that registers `apply_rule` gets the gate automatically — nothing to remember.

**ToolRegistry is an instance, not a module global.**
The decorator is a method on the instance: `@registry.tool(...)`. The instance is passed explicitly to `Agent`. Two agents with different tool sets can coexist in the same process without their registries colliding. A module-level global would make that impossible.

**Sliding window over summarisation.**
`SlidingWindowMemory` keeps the last 20 messages in a plain list; `messages()` prepends the system prompt on every call so it's never evicted. The agent appends tool-role messages directly to `_messages` (bypassing `add()`) to preserve the `tool_call_id` field the OpenAI API requires. Summarisation would need an extra LLM call every time the window fills — unnecessary for an agent that typically runs 5–8 tool calls.

### Why each decision, and what breaks if you choose wrong

| Decision | Why | What breaks if you don't |
|---|---|---|
| `ToolRegistry` as instance, not global | Two agents can coexist in the same process | Module-level global: both agents share one tool namespace — silent collision, no error raised |
| Approval gate on the tool (`require_human_approval=True`) | Policy co-located with the dangerous action | Gate on the `Agent`: every new agent author must remember to add gate logic; `apply_rule` can be registered without it |
| ReAct loop over fixed phases | Non-deterministic tool selection = genuine agency | Fixed pipeline: call order is hardcoded; LLM cannot adapt based on what data it has seen |
| Sliding window over summarisation | No extra LLM calls on window fill | Summarisation requires an additional LLM call every time the window fills — unnecessary for 5–8 tool call agents |

**Three exit conditions.**
The loop runs for `max_iterations`. It exits early when the LLM returns text with no tool calls (done), or when the same tool fails 3 consecutive times (`consecutive_errors >= 3` — checked after each tool call within an iteration). The counter resets to 0 on any successful call, so a tool that occasionally errors won't trigger a false stop.

---

## Development Approach

### Coding agent and workflow

RuleSmith was built with **Claude Code** (`claude-sonnet-4-6`) via the Claude Code CLI — an AI coding agent that reads, writes, and edits files, runs shell commands, and holds a multi-turn conversation with the developer inside the terminal.

The workflow was conversational and iterative rather than prompt-and-paste. Instead of generating a complete file in one shot, the agent was engaged in back-and-forth: asked to explain a decision, challenged on an API choice, redirected when a proposed design had a flaw. The agent proposed, the developer reviewed the plan before any file was created, and only then did code get written. This kept the human in the loop at the architecture level while delegating the mechanical work — writing schemas, wiring constructors, formatting trace output — to the agent.

### Choosing the example problem

Five candidate agent examples were sketched and scored before a line of code was written. The evaluation criterion was whether the example genuinely required agency — an unpredictable, data-driven tool-call path — or whether it was just a fixed pipeline dressed up as an agent.

RuleSmith scored highest because its investigation path is genuinely non-deterministic: the LLM may call `get_events_by_type` for deeper threshold analysis, or decide the execution logs alone are sufficient to propose a rule. That branch is not scripted anywhere in the code. It emerges from the LLM reasoning over the data it has seen so far. Candidates that were dropped included a log-triage agent (fixed three-step pipeline) and a code-review agent (would have required a real repository as input, complicating the demo).

Spring AI was considered and dropped separately: its `ChatClient` + `@Tool` annotations are themselves an agent framework, which would have violated the assignment constraint of building from primitives.

### How the solution evolved

The framework was built bottom-up in five stages, each stage driving out API issues before the next was started:

1. **`llm.py`** — confirm the HAI proxy connection and the raw message format. Everything downstream depends on this working.
2. **`tool.py`** — implement the registry, the `@tool` decorator, OpenAI schema generation, and the approval gate. The gate was originally sketched on the `Agent`, but moved to the tool during the planning review (see below).
3. **`memory.py`** — sliding window with an always-prepended system prompt. The decision to append tool-role messages directly (bypassing `add()`) to preserve `tool_call_id` was discovered here, not planned upfront.
4. **`tracer.py`** — append-only execution log. Kept intentionally dumb — a list of typed steps, no external dependencies.
5. **`agent.py`** — the ReAct loop. Consumed all four components as a client, which surfaced two API rough edges (the error counter reset rule; the need for a distinct `consecutive_errors` counter separate from the iteration counter) that were fixed before the example agent was written.

The example agent (`rulesmith.py`) was written last and treated as a consumer acceptance test for the framework. Any friction in registering tools, reading trace output, or handling rejections pointed to a framework fix, not a workaround in the example.

**Two design decisions changed during the planning review, before any code was written:**

- The registry went from a module-level global to an instance. A global makes two agents in the same process share tool namespaces — ruled out immediately once the multi-agent future improvement was sketched.
- The approval gate moved from the agent to the tool. Putting it on the agent means every new agent author must remember to add gate logic. Putting it on the tool (via `require_human_approval=True`) means the policy travels with `apply_rule` automatically.

### Validation

Validation happened at two levels.

**Behavioural validation** was done by running the agent end-to-end against the mock data and reading the printed `ExecutionTrace`. Each run was checked for: correct tool-call ordering (no `apply_rule` before `suggest_rule`), approval gate triggering exactly once, rejection handling (the agent continued rather than crashing when `apply_rule` was denied), and the final rationale referencing actual data from the tool results rather than hallucinated values.

**Framework validation** was done by deliberately exercising edge cases during development: calling a tool that doesn't exist (registry raises `KeyError`), exhausting `max_iterations` (loop exits cleanly with the last text response), and triggering three consecutive tool errors (loop exits with an error summary rather than hanging). These were tested interactively, not via a test suite — the framework has no automated tests, which is noted in Future Improvements as the highest-value gap to close.

---

## Future Improvements

**Semantic event store with embeddings.**
Right now `get_execution_logs` returns a flat list of historical interventions filtered by event type. A better approach: embed every historical event (type, threshold values, operator action, outcome) into a vector store. The agent could then run a similarity search — "find past events most similar to the current unmatched pattern" — rather than filtering by exact event type. This would surface precedents the agent currently misses: a MEMORY_PRESSURE event handled identically to MEMORY_GUARD, for instance, would never appear in a type-exact filter but would rank highly in an embedding search. The `suggest_rule` rationale would be grounded in semantically similar history rather than just matching records. Not implemented now because it requires an embedding model, a vector store, and an ingestion pipeline — that's a separate system, not a framework primitive. The mock data approach keeps the demo self-contained and runnable offline.

**Persistent memory across runs.**
The sliding window resets every time the agent starts. If the agent ran yesterday and proposed a rule that was rejected, it has no memory of that today. A simple fix is to serialise the conversation history to a file or key-value store at the end of each run and reload it on the next. More useful would be persisting the `ExecutionTrace` — the agent could review its own past decisions before starting a new investigation, avoiding duplicate proposals. Skipped for now because it requires choosing a storage backend and wiring up load/save logic, which adds setup steps for anyone running the demo locally. It will be a bigger effort

**Multi-agent handoff.**
A single agent handles the full investigation today. A natural split would be a *Scanner* agent that identifies unmatched event patterns and hands off one pattern at a time to a *Proposer* agent that does the deep log analysis and rule drafting. The Scanner stays lightweight; the Proposer can have a narrower system prompt and tool set tuned for a single event type. The framework already supports multiple independent registries — the orchestration layer is the missing piece. 

**Streaming output.**
The current implementation blocks until the full LLM response arrives. Streaming would let the operator see the agent's reasoning tokens as they're generated, making long tool-call chains feel more transparent. The OpenAI SDK supports streaming natively; the main change needed is in `LLMClient.chat()` and how the loop handles partial messages. Left out because the printed `ExecutionTrace` already gives full visibility into every step after the fact, and streaming would complicate the loop logic without improving the demo's clarity.

**Test coverage.**
The framework has no tests. The highest-value targets would be `ToolRegistry.call()` (approval gate logic, rejection payload, error handling) and the `Agent` loop exit conditions (clean exit, max iterations, consecutive error counter). Both are pure Python with no external dependencies — straightforward to unit test.
