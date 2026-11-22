# IEP Event Taxonomy

## Overview

Events are classified into three groups: Resource events, Application events, and Database events.
Each event type has a canonical set of metric fields, a default severity, and a recommended action.

---

## Resource Events

| Event type | Key metric fields | Default severity | Has existing rule |
|-----------|------------------|-----------------|-------------------|
| `CPU_SPIKE` | `cpuUsage` (%) | HIGH | Yes |
| `DISK_FULL` | `diskUsage` (%) | CRITICAL | Yes |
| `MEMORY_GUARD` | `memoryUsage` (%) | HIGH | **No** |
| `SWAP_USAGE` | `swapUsage` (%) | HIGH | **No** |
| `NETWORK_TIMEOUT` | `timeouts` (count) | MEDIUM | Yes |

---

## Application Events

| Event type | Key metric fields | Default severity | Has existing rule |
|-----------|------------------|-----------------|-------------------|
| `SERVICE_DOWN` | `downtime` (seconds) | CRITICAL | Yes |
| `LATENCY_SPIKE` | `p99Latency` (ms) | HIGH | Yes |
| `HTTP_5XX` | `errorRate` (%) | HIGH | Yes |
| `THREAD_POOL` | `activeThreads` (count) | HIGH | Yes |
| `CACHE_MISS` | `missRate` (%) | LOW | Yes |
| `QUEUE_DEPTH` | `depth` (count) | MEDIUM | Yes |

---

## Database Events

| Event type | Key metric fields | Default severity | Has existing rule |
|-----------|------------------|-----------------|-------------------|
| `DB_CONNECTION_POOL` | `poolUsage` (%) | MEDIUM | Yes |
| `GC_PAUSE` | `pauseMs` (ms) | LOW | Yes |
| `AUTH_FAILURE` | `failures` (count) | HIGH | Yes |

---

## Unmatched Event Types

The following two event types have **no existing rule** and generate unmatched events that operators
currently handle manually.

### `MEMORY_GUARD`

- **Metric:** `memoryUsage` (percentage of total heap/RSS)
- **Observed threshold range:** 80–93% across recent events
- **Historical operator response:** Manual alert raised by ops team and SRE bot; on-call paged when usage exceeds ~88%
- **Pattern:** Events cluster between 80–90%; anything above 90% has historically triggered immediate escalation
- **Recommended severity:** HIGH (CRITICAL when memoryUsage > 90)
- **Recommended action:** `CREATE_ALERT`
- **Recommended rule name:** `HIGH_MEMORY_GUARD_THRESHOLD`

### `SWAP_USAGE`

- **Metric:** `swapUsage` (percentage of total swap space)
- **Observed threshold range:** 60–79% across recent events
- **Historical operator response:** Service restart to prevent OOM; manual alert when swapUsage > 70%
- **Pattern:** Swap above 60% correlates with OOM risk; operators have restarted services at 70–78%
- **Recommended severity:** HIGH
- **Recommended action:** `PAGE_ONCALL`
- **Recommended rule name:** `HIGH_SWAP_USAGE_THRESHOLD`

---

## Notes

- Event types with no existing rule are the primary targets for RuleSmith's investigation.
- `MEMORY_GUARD` and `SWAP_USAGE` account for all unmatched events in the last 48h.
- Both types appear in `EXECUTION_LOGS` with repeated manual interventions — strong signal for rule creation.
