"""Lightweight observability for the web API: structured access logs and
Prometheus-format metrics, with no extra dependencies.

`METRICS` is a process-wide registry updated by the request middleware in
`main.py`; `render()` emits the standard Prometheus text exposition format so a
scraper (or a curl) can read counters and per-route latency at `/metrics`.
Access logs are emitted as one JSON object per request, so they drop straight
into any log pipeline.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict

# One JSON line per request. `message` is already JSON, so the formatter is bare.
access_logger = logging.getLogger("eurodata.web.access")
if not access_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    access_logger.addHandler(_handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False


def _labels(**pairs: str) -> str:
    inner = ",".join(f'{k}="{v}"' for k, v in pairs.items())
    return "{" + inner + "}"


class Metrics:
    """Thread-safe request counters and latency, labelled by method/route/status.

    Latency is a Prometheus *summary* (sum + count → derive averages); route
    labels use the matched path template (e.g. ``/api/series``), never the raw
    URL, so cardinality stays bounded.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self._dur_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._dur_count: dict[tuple[str, str], int] = defaultdict(int)

    def observe(self, method: str, route: str, status: int, duration_s: float) -> None:
        with self._lock:
            self._requests[(method, route, str(status))] += 1
            self._dur_sum[(method, route)] += duration_s
            self._dur_count[(method, route)] += 1

    def render(self) -> str:
        lines = [
            "# HELP eurodata_http_requests_total Total HTTP requests handled.",
            "# TYPE eurodata_http_requests_total counter",
        ]
        with self._lock:
            for (method, route, status), n in sorted(self._requests.items()):
                lines.append("eurodata_http_requests_total"
                             + _labels(method=method, route=route, status=status)
                             + f" {n}")
            lines += [
                "# HELP eurodata_http_request_duration_seconds Request duration summary.",
                "# TYPE eurodata_http_request_duration_seconds summary",
            ]
            for (method, route), total in sorted(self._dur_sum.items()):
                labels = _labels(method=method, route=route)
                lines.append(f"eurodata_http_request_duration_seconds_sum{labels} {total}")
                lines.append("eurodata_http_request_duration_seconds_count"
                             + labels + f" {self._dur_count[(method, route)]}")
        return "\n".join(lines) + "\n"


METRICS = Metrics()
