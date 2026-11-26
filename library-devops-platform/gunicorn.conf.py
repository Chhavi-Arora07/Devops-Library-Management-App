"""One worker with threads: metrics stay accurate and we scale by adding pods."""
import os

from prometheus_client import start_http_server

bind = "0.0.0.0:8000"
workers = 1
worker_class = "gthread"
threads = 8
timeout = 30
graceful_timeout = 20
worker_tmp_dir = os.environ.get("WORKER_TMP_DIR", "/tmp")  # nosec B108


def post_worker_init(worker):
    # Metrics use a separate port that is never exposed to library users.
    start_http_server(int(os.environ.get("METRICS_PORT", "9100")))
