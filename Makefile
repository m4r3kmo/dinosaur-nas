include versions.mk

.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

.PHONY: help

help:
	@echo "Dinosaur NAS Infrastructure"
	@echo ""
	@echo "Cluster management:"
	@echo "  make status              - Cluster overview"
	@echo "  make nodes               - Kubernetes nodes"
	@echo "  make pods                - Kubernetes pods"
	@echo "  make services            - Kubernetes services"
	@echo "  make releases            - Helm releases"
	@echo ""
	@echo "NVIDIA GPU:"
	@echo "  make gpu                 - NVIDIA GPU status"
	@echo "  make bootstrap-nvidia    - Install NVIDIA Container Toolkit"
	@echo "  make gpu-runtime         - Verify NVIDIA runtime"
	@echo "  make template-nvidia     - Render NVIDIA Helm templates"
	@echo "  make deploy-nvidia       - Deploy NVIDIA Device Plugin"
	@echo "  make test-gpu            - Run GPU smoke test"
	@echo "  make clean-gpu-test      - Remove GPU smoke test"
	@echo ""
	@echo "Storage infrastructure:"
	@echo "  make storage-status     - Disk and filesystem overview"
	@echo "  make storage-init       - Initialize disks (DESTRUCTIVE)"
	@echo "  make storage-mount      - Mount NAS storage"
	@echo "  make storage-verify     - Verify NAS storage"
	@echo "  make storage-dependencies - Configure K3s storage dependencies"
	@echo "  make storage-layout     - Create media directories"
	@echo "  make lint-storage       - Validate storage Helm chart"
	@echo "  make template-storage   - Render storage Helm templates"
	@echo "  make deploy-storage     - Deploy Kubernetes storage"
	@echo "  make test-storage       - Run storage smoke test"
	@echo "  make clean-storage-test - Remove storage smoke test"
	@echo ""
	@echo "Jellyfin:"
	@echo "  make lint-jellyfin       - Validate Helm chart"
	@echo "  make template-jellyfin   - Render Helm templates"
	@echo "  make deploy-jellyfin     - Deploy Jellyfin"
	@echo "  make status-jellyfin     - Jellyfin status"
	@echo "  make logs-jellyfin       - Follow Jellyfin logs"
	@echo ""
	@echo "Samba SMB:"
	@echo "  make lint-samba          - Validate Helm chart"
	@echo "  make template-samba      - Render Helm templates"
	@echo "  make deploy-samba        - Deploy Samba"
	@echo "  make status-samba        - Samba status"
	@echo "  make logs-samba          - Follow Samba logs"
	@$(MAKE) --no-print-directory help-downloader
	@$(MAKE) --no-print-directory help-cert-manager
	@$(MAKE) --no-print-directory help-pki

# ---------------------------------------------------------------------------
# Cluster management
# ---------------------------------------------------------------------------

.PHONY: status nodes pods services releases

status: nodes pods services releases

nodes:
	kubectl get nodes -o wide

pods:
	kubectl get pods -A

services:
	kubectl get svc -A

releases:
	helm list -A

# ---------------------------------------------------------------------------
# NVIDIA GPU bootstrap
# ---------------------------------------------------------------------------

.PHONY: gpu bootstrap-nvidia gpu-runtime

gpu:
	nvidia-smi

bootstrap-nvidia:
	bash scripts/bootstrap/nvidia-toolkit.sh "$(NVIDIA_TOOLKIT_VERSION)"

gpu-runtime:
	kubectl get runtimeclass
	sudo grep -i nvidia /var/lib/rancher/k3s/agent/etc/containerd/config.toml

# ---------------------------------------------------------------------------
# NVIDIA Device Plugin
# ---------------------------------------------------------------------------

.PHONY: deploy-nvidia template-nvidia

deploy-nvidia:
	helm upgrade --install nvidia-device-plugin \
		nvdp/nvidia-device-plugin \
		--version $(NVIDIA_DEVICE_PLUGIN_VERSION) \
		--namespace gpu-system \
		--create-namespace \
		-f infrastructure/nvidia/values.yaml \
		--wait \
		--timeout 5m

template-nvidia:
	helm template nvidia-device-plugin \
		nvdp/nvidia-device-plugin \
		--version $(NVIDIA_DEVICE_PLUGIN_VERSION) \
		--namespace gpu-system \
		-f infrastructure/nvidia/values.yaml
# ---------------------------------------------------------------------------
# NVIDIA GPU smoke test
# ---------------------------------------------------------------------------

.PHONY: test-gpu clean-gpu-test

test-gpu:
	helm upgrade --install gpu-smoke-test \
		./infrastructure/nvidia/smoke-test \
		--namespace gpu-system \
		--wait \
		--wait-for-jobs \
		--timeout 5m
	kubectl logs -n gpu-system job/gpu-smoke-test

clean-gpu-test:
	helm uninstall gpu-smoke-test --namespace gpu-system
# ---------------------------------------------------------------------------
# Storage infrastructure
# ---------------------------------------------------------------------------

.PHONY: storage-status storage-init

storage-status:
	lsblk -o NAME,SIZE,MODEL,SERIAL,FSTYPE,UUID,MOUNTPOINTS
	df -hT

storage-init:
	sudo bash scripts/storage/prepare-disks.sh "$(CONFIRM)"

.PHONY: storage-mount storage-verify storage-dependencies

storage-mount:
	sudo bash scripts/storage/mount-storage.sh

storage-verify:
	bash scripts/storage/verify-storage.sh

storage-dependencies: storage-verify
	sudo mkdir -p /etc/systemd/system/k3s.service.d
	sudo install -m 644 infrastructure/systemd/k3s-storage.conf \
		/etc/systemd/system/k3s.service.d/storage.conf
	sudo systemctl daemon-reload

# ---------------------------------------------------------------------------
# Kubernetes storage
# ---------------------------------------------------------------------------

.PHONY: storage-layout lint-storage template-storage deploy-storage

storage-layout: storage-verify
	sudo install -d -m 2775 \
		-o "$$(id -u)" -g "$$(id -g)" \
		/mnt/storage/media \
		/mnt/storage/media/movies \
		/mnt/storage/media/series \
		/mnt/storage/media/music

lint-storage:
	helm lint ./storage/nas-storage

template-storage:
	helm template nas-storage \
		./storage/nas-storage \
		--namespace media

deploy-storage: storage-layout lint-storage
	helm upgrade --install nas-storage \
		./storage/nas-storage \
		--namespace media \
		--create-namespace

# ---------------------------------------------------------------------------
# Storage smoke test
# ---------------------------------------------------------------------------

.PHONY: test-storage clean-storage-test

test-storage:
	helm upgrade --install storage-smoke-test \
		./storage/smoke-test \
		--namespace media \
		--set securityContext.runAsUser="$$(id -u)" \
		--set securityContext.runAsGroup="$$(id -g)" \
		--wait \
		--wait-for-jobs \
		--timeout 5m
	kubectl logs -n media job/storage-smoke-test

clean-storage-test:
	helm uninstall storage-smoke-test --namespace media

# ---------------------------------------------------------------------------
# Jellyfin
# ---------------------------------------------------------------------------

.PHONY: lint-jellyfin template-jellyfin deploy-jellyfin status-jellyfin logs-jellyfin

lint-jellyfin:
	helm lint ./apps/jellyfin

template-jellyfin:
	helm template jellyfin \
		./apps/jellyfin \
		--namespace media

deploy-jellyfin: storage-verify lint-jellyfin
	helm upgrade --install jellyfin \
		./apps/jellyfin \
		--namespace media \
		--create-namespace \
		--wait \
		--timeout 10m

status-jellyfin:
	kubectl get deployment,pods,svc,pvc -n media -o wide

logs-jellyfin:
	kubectl logs -n media deployment/jellyfin --tail=100 -f

# ---------------------------------------------------------------------------
# Samba SMB
# ---------------------------------------------------------------------------

.PHONY: lint-samba template-samba deploy-samba status-samba logs-samba

lint-samba:
	helm lint ./apps/samba

template-samba:
	helm template samba \
		./apps/samba \
		--namespace media

deploy-samba: storage-verify lint-samba
	helm upgrade --install samba \
		./apps/samba \
		--namespace media \
		--wait \
		--timeout 5m

status-samba:
	kubectl get deployment,pods,svc -n media -o wide

logs-samba:
	kubectl logs -n media deployment/samba --tail=100 -f

# ---------------------------------------------------------------------------
# Dinosaur Downloader
# ---------------------------------------------------------------------------

include make/downloader.mk

# ---------------------------------------------------------------------------
# Certificate management
# ---------------------------------------------------------------------------

include make/cert-manager.mk