#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

source "${ROOT_DIR}/storage/disks.conf"

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: Run this script as root."
    exit 1
fi

if [[ "${1:-}" != "ERASE-WD-REDS" ]]; then
    echo "ERROR: Explicit erase confirmation required."
    exit 1
fi

validate_disk() {
    local disk="$1"
    local expected_serial="$2"

    if [[ ! -b "$disk" ]]; then
        echo "ERROR: Disk not found: $disk"
        exit 1
    fi

    local actual_serial
    actual_serial="$(lsblk -dn -o SERIAL "$disk" | xargs)"

    if [[ "$actual_serial" != "$expected_serial" ]]; then
        echo "ERROR: Serial number mismatch."
        exit 1
    fi

    if [[ "$(lsblk -dn -o TYPE "$disk")" != "disk" ]]; then
        echo "ERROR: Device is not a physical disk."
        exit 1
    fi

    if lsblk -nr -o MOUNTPOINTS "$disk" | grep -q '[^[:space:]]'; then
        echo "ERROR: Disk contains mounted partitions."
        exit 1
    fi

    if lsblk -nr -o TYPE "$disk" | grep -qvE '^(disk|part)$'; then
        echo "ERROR: Disk has active device mappings."
        exit 1
    fi

    if [[ "$(blkid -p -s TYPE -o value "${disk}-part1")" != "ntfs" ]]; then
        echo "ERROR: Expected original NTFS partition."
        echo "Disk may already be initialized."
        exit 1
    fi

    echo "Validated: $disk"
}

prepare_disk() {
    local disk="$1"
    local label="$2"

    echo "Preparing disk: $disk"

    parted -s "$disk" \
        mklabel gpt \
        mkpart primary ext4 1MiB 100%

    partprobe "$disk"
    udevadm settle

    local partition="${disk}-part1"

    if [[ ! -b "$partition" ]]; then
        echo "ERROR: Partition not found."
        exit 1
    fi

    wipefs -a "$partition"

    mkfs.ext4 -m 0 -L "$label" "$partition"

    echo "Successfully formatted: $partition"
}

# Validate both disks before making any changes.
validate_disk "$DISK1" "DISK1_SERIAL"
validate_disk "$DISK2" "DISK2_SERIAL"

prepare_disk "$DISK1" "$DISK1_LABEL"
prepare_disk "$DISK2" "$DISK2_LABEL"

echo "Storage initialization completed."