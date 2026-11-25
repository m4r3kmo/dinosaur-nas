#!/usr/bin/env bash
set -euo pipefail

for path in /mnt/disk1 /mnt/disk2 /mnt/storage; do
    if mountpoint -q "$path"; then
        echo "OK: $path"
    else
        echo "ERROR: $path is not mounted."
        exit 1
    fi
done

if [[ "$(findmnt -n -o FSTYPE --mountpoint /mnt/storage)" != "fuse.mergerfs" ]]; then
    echo "ERROR: Storage is not a mergerfs pool."
    exit 1
fi

df -hT /mnt/disk1 /mnt/disk2 /mnt/storage

echo "Storage verification successful."