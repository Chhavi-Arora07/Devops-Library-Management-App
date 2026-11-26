"""Structured JSON logs, request IDs, Prometheus metrics and security headers."""
import json
import logging
import re
import sys
import time
import uuid

from flask import Flask, g, request
from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["route"])
LOANS = Counter("library_loans_total", "Loan operations", ["action"])
BUILD_INFO = Gauge("library_build_info", "Running version", ["version"])

# Probe traffic is excluded so it cannot hide a rise in real user errors.
UNMETERED = {"/healthz", "/readyz"}
SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def init_observability(app: Flask) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("library")
    log.handlers = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False
    BUILD_INFO.labels(app.config["LIBRARY"].version).set(1)

    @app.before_request
    def start_timer():
        g.started = time.perf_counter()
        supplied = request.headers.get("X-Request-ID", "")
        g.request_id = supplied if SAFE_REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex

    @app.after_request
    def record(response):
        response.headers["X-Request-ID"] = g.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        if request.path in UNMETERED:
            return response
        route = request.url_rule.rule if request.url_rule else "unmatched"
        elapsed = time.perf_counter() - g.started
        REQUESTS.labels(request.method, route, response.status_code).inc()
        LATENCY.labels(route).observe(elapsed)
        # Route templates only: no query strings, bodies or member details.
        log.info("request", extra={"fields": {
            "request_id": g.request_id, "method": request.method, "route": route,
            "status": response.status_code, "duration_ms": round(elapsed * 1000, 2),
        }})
        return response
