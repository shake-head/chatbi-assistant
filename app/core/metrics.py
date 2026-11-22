"""Prometheus metrics shared by HTTP middleware and the AI gateway."""

from prometheus_client import Counter, Histogram

HTTP_REQUESTS_TOTAL = Counter(
    "chatbi_http_requests_total",
    "HTTP requests handled by the API.",
    ["method", "path", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "chatbi_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path"],
)
AI_REQUESTS_TOTAL = Counter(
    "chatbi_ai_requests_total",
    "AI gateway calls by operation, provider, and result.",
    ["operation", "provider", "status"],
)
AI_COST_USD_TOTAL = Counter(
    "chatbi_ai_cost_usd_total",
    "Estimated AI cost in USD.",
    ["operation", "provider"],
)
