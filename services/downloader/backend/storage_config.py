import os

from pathlib import Path


NAS_MOUNT_PATH = Path(
    os.getenv("NAS_MOUNT_PATH", "/mnt/storage")
)


def storage_mounted():
    mount_path = str(NAS_MOUNT_PATH.resolve())

    try:
        with open("/proc/self/mountinfo") as mounts:
            return any(
                line.split()[4] == mount_path
                for line in mounts
            )
    except OSError:
        return False