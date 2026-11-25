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