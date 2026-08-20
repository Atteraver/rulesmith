from datetime import datetime, timedelta, timezone

# 14 existing rules
RULES = [
    {"id": "rule-001", "condition": "eventType=CPU_SPIKE AND cpuUsage > 90", "action": "CREATE_ALERT", "severity": "HIGH"},
    {"id": "rule-002", "condition": "eventType=DISK_FULL AND diskUsage > 95", "action": "EMAIL_OPS", "severity": "CRITICAL"},
    {"id": "rule-003", "condition": "eventType=SERVICE_DOWN AND downtime > 60", "action": "PAGE_ONCALL", "severity": "CRITICAL"},
    {"id": "rule-004", "condition": "eventType=LATENCY_SPIKE AND p99Latency > 2000", "action": "CREATE_ALERT", "severity": "HIGH"},
    {"id": "rule-005", "condition": "eventType=DB_CONNECTION_POOL AND poolUsage > 85", "action": "CREATE_ALERT", "severity": "MEDIUM"},
    {"id": "rule-006", "condition": "eventType=HTTP_5XX AND errorRate > 5", "action": "CREATE_ALERT", "severity": "HIGH"},
    {"id": "rule-007", "condition": "eventType=CPU_SPIKE AND cpuUsage > 70", "action": "LOG_WARNING", "severity": "MEDIUM"},
    {"id": "rule-008", "condition": "eventType=DISK_FULL AND diskUsage > 80", "action": "LOG_WARNING", "severity": "LOW"},
    {"id": "rule-009", "condition": "eventType=NETWORK_TIMEOUT AND timeouts > 10", "action": "CREATE_ALERT", "severity": "MEDIUM"},
    {"id": "rule-010", "condition": "eventType=AUTH_FAILURE AND failures > 5", "action": "BLOCK_IP", "severity": "HIGH"},
    {"id": "rule-011", "condition": "eventType=QUEUE_DEPTH AND depth > 1000", "action": "EMAIL_OPS", "severity": "MEDIUM"},
    {"id": "rule-012", "condition": "eventType=GC_PAUSE AND pauseMs > 500", "action": "LOG_WARNING", "severity": "LOW"},
    {"id": "rule-013", "condition": "eventType=THREAD_POOL AND activeThreads > 90", "action": "CREATE_ALERT", "severity": "HIGH"},
    {"id": "rule-014", "condition": "eventType=CACHE_MISS AND missRate > 40", "action": "LOG_WARNING", "severity": "LOW"},
]

# Simulate timestamps over the last 48h
_now = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)

def _ts(hours_ago: float) -> str:
    return (_now - timedelta(hours=hours_ago)).isoformat()


RECENT_EVENTS = (
    # 23 MEMORY_GUARD events — no matching rule
    [{"id": f"evt-{100+i}", "type": "MEMORY_GUARD", "memoryUsage": 82 + (i % 12),
      "matchedRule": None, "timestamp": _ts(i * 0.9)} for i in range(23)]
    +
    # 18 SWAP_USAGE events — no matching rule
    [{"id": f"evt-{200+i}", "type": "SWAP_USAGE", "swapUsage": 60 + (i % 20),
      "matchedRule": None, "timestamp": _ts(i * 1.1)} for i in range(18)]
    +
    # ~800 events that matched existing rules (abbreviated)
    [{"id": f"evt-{500+i}", "type": "CPU_SPIKE", "cpuUsage": 85 + (i % 10),
      "matchedRule": "rule-001", "timestamp": _ts(i * 0.3)} for i in range(200)]
    +
    [{"id": f"evt-{700+i}", "type": "HTTP_5XX", "errorRate": 6 + (i % 5),
      "matchedRule": "rule-006", "timestamp": _ts(i * 0.4)} for i in range(150)]
    +
    [{"id": f"evt-{900+i}", "type": "LATENCY_SPIKE", "p99Latency": 2100 + (i * 50),
      "matchedRule": "rule-004", "timestamp": _ts(i * 0.5)} for i in range(100)]
)

EXECUTION_LOGS = [
    {"eventType": "MEMORY_GUARD", "timestamp": _ts(2), "outcome": "MANUAL_ALERT_RAISED",
     "operator": "ops-team", "note": "Manually paged on-call, memoryUsage was 91%"},
    {"eventType": "MEMORY_GUARD", "timestamp": _ts(6), "outcome": "MANUAL_ALERT_RAISED",
     "operator": "ops-team", "note": "Second occurrence within 6h, memory at 88%"},
    {"eventType": "MEMORY_GUARD", "timestamp": _ts(14), "outcome": "MANUAL_ALERT_RAISED",
     "operator": "ops-team", "note": "Pattern recurs, memoryUsage 93%"},
    {"eventType": "MEMORY_GUARD", "timestamp": _ts(22), "outcome": "MANUAL_ALERT_RAISED",
     "operator": "sre-bot", "note": "Auto-escalation triggered by operator runbook"},
    {"eventType": "MEMORY_GUARD", "timestamp": _ts(30), "outcome": "MANUAL_ALERT_RAISED",
     "operator": "ops-team"},
    {"eventType": "SWAP_USAGE", "timestamp": _ts(4), "outcome": "SERVICE_RESTART",
     "operator": "ops-team", "note": "High swap caused OOM risk, service restarted"},
    {"eventType": "SWAP_USAGE", "timestamp": _ts(18), "outcome": "SERVICE_RESTART",
     "operator": "sre-bot", "note": "swapUsage 78%, restart prevented OOM"},
    {"eventType": "SWAP_USAGE", "timestamp": _ts(36), "outcome": "MANUAL_ALERT_RAISED",
     "operator": "ops-team"},
]
