#!/usr/bin/env python3

import csv
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path

directory = Path("/run/dinosaur-metrics")
output = directory / "nvidia.prom"

metrics = [
    ("temperature.gpu", "temperature_celsius", 1),
    ("utilization.gpu", "utilization_percent", 1),
    ("utilization.memory", "memory_utilization_percent", 1),
    ("memory.total", "memory_total_bytes", 1048576),
    ("memory.used", "memory_used_bytes", 1048576),
    ("fan.speed", "fan_percent", 1),
    ("power.draw", "power_watts", 1),
    ("utilization.encoder", "encoder_percent", 1),
    ("utilization.decoder", "decoder_percent", 1),
]

def escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

def collect():
    fields = ["uuid", "name"] + [m[0] for m in metrics]

    result = subprocess.check_output(
        [
            "/usr/bin/nvidia-smi",
            "--query-gpu=" + ",".join(fields),
            "--format=csv,noheader,nounits",
        ],
        text=True,
        timeout=10,
    )

    lines = []

    for row in csv.reader(result.splitlines()):
        if len(row) != len(fields):
            raise RuntimeError("Unexpected nvidia-smi output")

        uuid = escape(row[0].strip())
        name = escape(row[1].strip())
        labels = f'uuid="{uuid}",model="{name}"'

        for value, (_, metric, multiplier) in zip(row[2:], metrics):
            try:
                number = float(value.strip()) * multiplier
            except ValueError:
                continue

            if math.isfinite(number):
                lines.append(
                    f"dinosaur_gpu_{metric}{{{labels}}} {number}"
                )

    if not lines:
        raise RuntimeError("No GPU metrics collected")

    lines.append(
        f"dinosaur_gpu_collection_timestamp_seconds {time.time()}"
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=directory,
        delete=False,
    ) as temp:
        temp.write("\n".join(lines) + "\n")
        temp_path = temp.name

    os.chmod(temp_path, 0o644)
    os.replace(temp_path, output)

try:
    collect()
except Exception:
    output.unlink(missing_ok=True)
    raise
