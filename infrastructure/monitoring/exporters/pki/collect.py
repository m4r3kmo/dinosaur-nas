#!/usr/bin/env python3

import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

pki = Path("/etc/dinosaur-nas/pki")
directory = Path("/run/dinosaur-metrics")
output = directory / "pki.prom"

certificates = {
    "root": pki / "dinosaur-ca.crt",
    "intermediate": pki / "dinosaur-intermediate-ca.crt",
}


def certificate_date(path, option):
    result = subprocess.check_output(
        [
            "/usr/bin/openssl",
            "x509",
            "-in", str(path),
            "-noout",
            option,
        ],
        text=True,
        timeout=10,
        env={**os.environ, "LC_ALL": "C"},
    )

    value = result.strip().split("=", 1)[1]

    return datetime.strptime(
        value, "%b %d %H:%M:%S %Y GMT"
    ).replace(tzinfo=timezone.utc).timestamp()


def collect():
    lines = [
        "# TYPE dinosaur_pki_ca_expiration_timestamp_seconds gauge",
        "# TYPE dinosaur_pki_ca_issued_timestamp_seconds gauge",
    ]

    for name, path in certificates.items():
        expiration = certificate_date(path, "-enddate")
        issued = certificate_date(path, "-startdate")

        lines.extend([
            f'dinosaur_pki_ca_expiration_timestamp_seconds{{ca="{name}"}} {expiration}',
            f'dinosaur_pki_ca_issued_timestamp_seconds{{ca="{name}"}} {issued}',
        ])

    lines.append(
        f"dinosaur_pki_collection_timestamp_seconds {time.time()}"
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
