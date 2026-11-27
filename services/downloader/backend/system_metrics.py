import json
import math
import os
import logging

from urllib.parse import urlencode
from urllib.request import urlopen

logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "http://dinosaur-monitoring-prometheus.monitoring.svc.cluster.local:9090",
).rstrip("/")

QUERIES = {
    "cpu_temp": (
        'node_hwmon_temp_celsius'
        '{chip="platform_coretemp_0",sensor="temp1"}'
    ),
    "gpu_temp": "dinosaur_gpu_temperature_celsius",
    "ram_usage": (
        '100 * (1 - '
        'node_memory_MemAvailable_bytes{job="node-exporter"} / '
        'node_memory_MemTotal_bytes{job="node-exporter"})'
    ),
}


def read_metric(query: str) -> float | None:
    url = (
        f"{PROMETHEUS_URL}/api/v1/query?"
        + urlencode({"query": query})
    )

    try:
        with urlopen(url, timeout=2) as response:
            payload = json.load(response)

        if payload.get("status") != "success":
            return None

        results = payload["data"]["result"]

        values = [
            float(result["value"][1])
            for result in results
        ]

        values = [
            value for value in values
            if math.isfinite(value)
        ]

        return round(max(values), 1) if values else None

    except Exception as exc:
        logger.debug("Prometheus query failed: %s", exc)
        return None


def get_system_metrics() -> dict:
    return {
        name: read_metric(query)
        for name, query in QUERIES.items()
    }
