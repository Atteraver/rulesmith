# IEP Allowed Actions

## Valid Action Strings

Only the following action strings may be used in IEP rules. Any other value will be rejected
by the rule engine at application time.

| Action | Description | Typical severity |
|--------|-------------|-----------------|
| `CREATE_ALERT` | Creates an alert in the ops dashboard. Ops team reviews asynchronously. | MEDIUM, HIGH |
| `PAGE_ONCALL` | Immediately pages the on-call engineer via PagerDuty. | HIGH, CRITICAL |
| `AUTO_RESTART` | Automatically restarts the affected service. Requires explicit approval. | CRITICAL only |
| `LOG_ONLY` | Writes a structured log entry. No human notification. | LOW |
| `SCALE_UP` | Triggers horizontal scale-up of the affected service. | HIGH, CRITICAL |
| `EMAIL_OPS` | Sends an email to the ops distribution list. | MEDIUM, CRITICAL |
| `BLOCK_IP` | Blocks a source IP at the network edge. | HIGH (auth events only) |

---

## When to Use Each Action

### `CREATE_ALERT`
Use for resource threshold events where human review is needed but immediate action is not.
Examples: `MEMORY_GUARD`, `CPU_SPIKE`, `LATENCY_SPIKE`, `HTTP_5XX`, `THREAD_POOL`, `QUEUE_DEPTH`.
Appropriate when the ops team can investigate within 5–15 minutes.

**`MEMORY_GUARD` → `CREATE_ALERT`** — memory guard events indicate elevated usage that requires
monitoring. An alert gives ops visibility to investigate before the situation becomes critical.

### `PAGE_ONCALL`
Use for events that indicate imminent service impact or OOM risk. The on-call engineer must be
woken immediately.
Examples: `SERVICE_DOWN`, `SWAP_USAGE`, `DISK_FULL` (CRITICAL).

**`SWAP_USAGE` → `PAGE_ONCALL`** — high swap usage is a leading indicator of OOM. Historical
execution logs show operators manually restarting services after swap exceeded 70%. Paging on-call
immediately prevents uncontrolled OOM crashes.

### `AUTO_RESTART`
Use only for CRITICAL events where a service is already unresponsive and no data loss risk exists.
**Do not use `AUTO_RESTART` for memory events (`MEMORY_GUARD`, `SWAP_USAGE`) without explicit human
approval** — a restart during active processing can cause data loss or incomplete transactions.
Memory events should use `CREATE_ALERT` or `PAGE_ONCALL` instead.

### `LOG_ONLY`
Use for LOW severity informational events where no human action is needed.
Examples: `GC_PAUSE` (low threshold), `CACHE_MISS`, `DISK_FULL` (early warning).

### `SCALE_UP`
Use for sustained HIGH load where adding capacity is the correct response.
Examples: `THREAD_POOL` (at scale), `QUEUE_DEPTH` (sustained backlog).
Not appropriate for memory events — scaling does not reduce per-instance memory pressure.

### `EMAIL_OPS`
Use for MEDIUM or CRITICAL events where async notification is sufficient but broader ops visibility
is needed. Examples: `DISK_FULL` (CRITICAL), `QUEUE_DEPTH` (MEDIUM).

### `BLOCK_IP`
Restricted to authentication-related events only (`AUTH_FAILURE`). Do not use for resource events.

---

## Action–Severity Matrix

| Action | LOW | MEDIUM | HIGH | CRITICAL |
|--------|-----|--------|------|---------|
| `LOG_ONLY` | ✓ | — | — | — |
| `CREATE_ALERT` | — | ✓ | ✓ | — |
| `EMAIL_OPS` | — | ✓ | — | ✓ |
| `PAGE_ONCALL` | — | — | ✓ | ✓ |
| `SCALE_UP` | — | — | ✓ | ✓ |
| `AUTO_RESTART` | — | — | — | ✓ (approval required) |
| `BLOCK_IP` | — | — | ✓ | — |

---

## Anti-Patterns

- **Do not** use `AUTO_RESTART` for `MEMORY_GUARD` or `SWAP_USAGE` events without human approval.
- **Do not** use `LOG_ONLY` for HIGH or CRITICAL severity events — silent failures are worse than noisy ones.
- **Do not** use `BLOCK_IP` for non-authentication events.
- **Do not** invent new action strings — the rule engine rejects unknown values at runtime.
