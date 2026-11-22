# IEP Rule Naming Conventions

## Naming Format

All IEP rules must follow the format:

```
<SEVERITY>_<COMPONENT>_<CONDITION>
```

Each segment is uppercase, separated by underscores. All three segments are required.

---

## Severity Levels

| Token | When to use |
|-------|-------------|
| `CRITICAL` | Service-threatening, requires immediate page. Data loss or full outage risk. |
| `HIGH` | Significant degradation, requires alert and investigation within minutes. |
| `MEDIUM` | Elevated condition, ops should be notified but no immediate action required. |
| `LOW` | Informational. Log only. No human action required. |

---

## Component Tokens

| Token | Covers |
|-------|--------|
| `MEMORY` | Heap, RSS, JVM memory, memory guards |
| `SWAP` | Swap space usage on host |
| `CPU` | CPU utilisation, load average |
| `DISK` | Disk space, inode exhaustion |
| `NETWORK` | Timeouts, packet loss, throughput |
| `DB` | Database connections, query latency |
| `APP` | Application-level metrics: HTTP errors, latency, thread pools |

---

## Condition Tokens

| Token | Meaning |
|-------|---------|
| `THRESHOLD` | A numeric metric has crossed a configured threshold |
| `SPIKE` | A sudden increase above baseline |
| `GUARD` | A guard condition tripped (e.g. memory guard threshold) |
| `EXHAUSTED` | Resource fully consumed |
| `PRESSURE` | Resource under sustained high load |
| `OVERFLOW` | Buffer or queue overflow |

---

## Examples

| Rule name | Event type | Rationale |
|-----------|-----------|-----------|
| `HIGH_MEMORY_GUARD_THRESHOLD` | `MEMORY_GUARD` | High severity, memory component, guard threshold tripped |
| `CRITICAL_SWAP_OVERFLOW` | `SWAP_USAGE` | Critical — OOM risk when swap is full |
| `HIGH_CPU_SPIKE_THRESHOLD` | `CPU_SPIKE` | High severity, CPU component, spike above threshold |
| `MEDIUM_DB_CONNECTION_THRESHOLD` | `DB_CONNECTION_POOL` | Medium severity, DB component |
| `HIGH_APP_LATENCY_THRESHOLD` | `LATENCY_SPIKE` | High severity, application latency |
| `LOW_MEMORY_PRESSURE` | `MEMORY_GUARD` | Low severity variant for early warning |

---

## Anti-Patterns

- **Do not** use the event type name directly as the rule name (e.g. `MEMORY_GUARD_RULE` is wrong).
- **Do not** omit the severity prefix — `MEMORY_GUARD_THRESHOLD` is invalid.
- **Do not** use abbreviations not in the token lists — `MEM`, `SWP`, `NET` are not valid component tokens.
- **Do not** use verbs — `CHECK_MEMORY` or `ALERT_ON_SWAP` are not valid formats.
- **Do not** mix cases — all tokens must be uppercase.
