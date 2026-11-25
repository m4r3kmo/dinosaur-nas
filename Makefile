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
	@echo "  make status           - Cluster overview"
	@echo "  make nodes            - Kubernetes nodes"
	@echo "  make pods             - Kubernetes pods"
	@echo "  make services         - Kubernetes services"
	@echo "  make releases         - Helm releases"
	@echo ""
	@echo "NVIDIA GPU:"
	@echo "  make gpu              - NVIDIA GPU status"
	@echo "  make bootstrap-nvidia - Install NVIDIA Container Toolkit"
	@echo "  make gpu-runtime      - Verify NVIDIA runtime"
	@echo "  make template-nvidia  - Render NVIDIA Helm templates"
	@echo "  make deploy-nvidia    - Deploy NVIDIA Device Plugin"

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