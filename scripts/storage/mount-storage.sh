#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: Run as root."
    exit 1
fi

source "${ROOT_DIR}/storage/disks.conf"

FSTAB_CONFIG="${ROOT_DIR}/storage/fstab.conf"

if [[ ! -f "$FSTAB_CONFIG" ]]; then
    echo "ERROR: Storage configuration not found."
    exit 1
fi

mkdir -p "$DISK1_MOUNT" "$DISK2_MOUNT" "$STORAGE_MOUNT"

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

# Remove previously managed storage configuration.
awk '
    /^# BEGIN DINOSAUR STORAGE$/ { skip=1; next }
    /^# END DINOSAUR STORAGE$/   { skip=0; next }
    !skip { print }
    END { if (skip) exit 1 }
' /etc/fstab > "$TMP_FILE"

# Remove trailing empty lines.
sed -i -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$TMP_FILE"

# Reject conflicting mount entries.
if awk '
    $1 !~ /^#/ &&
    ($2=="/mnt/disk1" ||
     $2=="/mnt/disk2" ||
     $2=="/mnt/storage") { found=1 }
    END { exit !found }
' "$TMP_FILE"; then
    echo "ERROR: Conflicting storage entries in fstab."
    exit 1
fi

# Append managed storage configuration.
{
    printf '\n# BEGIN DINOSAUR STORAGE\n'
    awk '{ print }' "$FSTAB_CONFIG"
    printf '# END DINOSAUR STORAGE\n'
} >> "$TMP_FILE"

# Validate fstab field count.
echo "Validating fstab syntax..."

awk '
    /^[[:space:]]*#/ || NF == 0 { next }
    NF != 6 {
        printf "ERROR: Invalid fstab entry at line %d: %s\n", NR, $0
        invalid=1
    }
    END { exit invalid }
' "$TMP_FILE"

# Verify generated fstab.
echo "Verifying generated fstab..."

findmnt --verify --verbose --tab-file "$TMP_FILE"

# Back up and update system fstab.
if ! cmp -s "$TMP_FILE" /etc/fstab; then
    BACKUP_FILE="/etc/fstab.backup.$(date +%Y%m%d-%H%M%S)"

    cp -a /etc/fstab "$BACKUP_FILE"
    install -m 644 "$TMP_FILE" /etc/fstab

    echo "Backup created: $BACKUP_FILE"
    echo "System fstab updated."
else
    echo "System fstab is already up to date."
fi

# Reload systemd mount units.
systemctl daemon-reload

# Mount physical disks.
echo "Mounting physical disks..."

systemctl start mnt-disk1.mount
systemctl start mnt-disk2.mount

# Mount mergerfs storage pool.
echo "Mounting mergerfs storage pool..."

systemctl start mnt-storage.mount

# Verify mounted storage.
bash "${ROOT_DIR}/scripts/storage/verify-storage.sh"

echo "Storage successfully mounted."