# ---------------------------------------------------------------------------
# Dinosaur Downloader
# ---------------------------------------------------------------------------

DOWNLOADER_NAMESPACE := media
DOWNLOADER_RELEASE := dinosaur-downloader
DOWNLOADER_IMAGE := localhost/dinosaur-downloader:$(DOWNLOADER_VERSION)
DOWNLOADER_CONTEXT := ./services/downloader
DOWNLOADER_CHART := ./apps/downloader
DOWNLOADER_LOCAL_PORT ?= 18085

.PHONY: help-downloader
.PHONY: lint-downloader template-downloader
.PHONY: build-downloader import-downloader
.PHONY: deploy-downloader update-downloader
.PHONY: restart-downloader status-downloader
.PHONY: logs-downloader port-forward-downloader
.PHONY: check-downloader-idle check-downloader-image
.PHONY: check-downloader-new-version

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help-downloader:
	@echo ""
	@echo "Dinosaur Downloader:"
	@echo "  make build-downloader        - Build container image"
	@echo "  make import-downloader       - Import image into K3s"
	@echo "  make lint-downloader         - Validate Helm chart"
	@echo "  make template-downloader     - Render Helm templates"
	@echo "  make deploy-downloader       - Deploy Downloader"
	@echo "  make update-downloader       - Build, import and deploy"
	@echo "  make restart-downloader      - Restart Downloader"
	@echo "  make status-downloader       - Check deployment status"
	@echo "  make logs-downloader         - Follow application logs"
	@echo "  make port-forward-downloader - Access web interface"

# ---------------------------------------------------------------------------
# Container image
# ---------------------------------------------------------------------------

build-downloader:
	podman build \
		--tag "$(DOWNLOADER_IMAGE)" \
		--file "$(DOWNLOADER_CONTEXT)/Dockerfile" \
		"$(DOWNLOADER_CONTEXT)"

import-downloader:
	@set -eu; \
	archive=$$(mktemp /tmp/dinosaur-downloader.XXXXXX.tar); \
	trap 'rm -f "$$archive"' EXIT; \
	podman save \
		--format oci-archive \
		--output "$$archive" \
		"$(DOWNLOADER_IMAGE)"; \
	sudo k3s ctr -n k8s.io images import "$$archive"
	$(MAKE) check-downloader-image

check-downloader-image:
	sudo k3s ctr -n k8s.io images list -q \
		| grep -Fx "$(DOWNLOADER_IMAGE)"

# ---------------------------------------------------------------------------
# Helm
# ---------------------------------------------------------------------------

lint-downloader:
	helm lint "$(DOWNLOADER_CHART)"

template-downloader:
	helm template "$(DOWNLOADER_RELEASE)" \
		"$(DOWNLOADER_CHART)" \
		--namespace "$(DOWNLOADER_NAMESPACE)" \
		--set-string image.tag="$(DOWNLOADER_VERSION)"

deploy-downloader: storage-verify lint-downloader check-downloader-image check-downloader-idle
	helm upgrade --install "$(DOWNLOADER_RELEASE)" \
		"$(DOWNLOADER_CHART)" \
		--namespace "$(DOWNLOADER_NAMESPACE)" \
		--set-string image.tag="$(DOWNLOADER_VERSION)" \
		--wait \
		--timeout 5m

# ---------------------------------------------------------------------------
# Update protection
# ---------------------------------------------------------------------------

check-downloader-idle:
	@set -eu; \
	replicas=$$(kubectl -n "$(DOWNLOADER_NAMESPACE)" get deployment "$(DOWNLOADER_RELEASE)" --ignore-not-found -o jsonpath='{.spec.replicas}'); \
	if [ -z "$$replicas" ] || [ "$$replicas" = "0" ]; then \
		echo "Downloader is not running"; \
	else \
		kubectl -n "$(DOWNLOADER_NAMESPACE)" exec deployment/"$(DOWNLOADER_RELEASE)" -- python -c 'import sqlite3,sys; db=sqlite3.connect("file:/state/downloads.db?mode=ro",uri=True); count=db.execute("SELECT COUNT(*) FROM downloads WHERE status IN (?,?) OR (status=? AND import_status IN (?,?))",("queued","running","completed","pending","scan_pending")).fetchone()[0]; sys.exit(f"Update blocked: {count} active or queued jobs") if count else print("Downloader is idle")'; \
	fi

check-downloader-new-version:
	@set -eu; \
	current=$$(kubectl -n "$(DOWNLOADER_NAMESPACE)" get deployment "$(DOWNLOADER_RELEASE)" --ignore-not-found -o jsonpath='{.spec.template.spec.containers[0].image}'); \
	if [ "$$current" = "$(DOWNLOADER_IMAGE)" ]; then \
		echo "Image version is already deployed."; \
		echo "Increase DOWNLOADER_VERSION in versions.mk first."; \
		exit 1; \
	fi

# ---------------------------------------------------------------------------
# Lifecycle management
# ---------------------------------------------------------------------------

update-downloader:
	$(MAKE) check-downloader-new-version
	$(MAKE) check-downloader-idle
	$(MAKE) build-downloader
	$(MAKE) import-downloader
	$(MAKE) deploy-downloader

restart-downloader: check-downloader-idle
	kubectl -n "$(DOWNLOADER_NAMESPACE)" rollout restart \
		deployment/"$(DOWNLOADER_RELEASE)"
	kubectl -n "$(DOWNLOADER_NAMESPACE)" rollout status \
		deployment/"$(DOWNLOADER_RELEASE)" \
		--timeout=180s

status-downloader:
	kubectl -n "$(DOWNLOADER_NAMESPACE)" \
		get deployment,pods,svc \
		-l app="$(DOWNLOADER_RELEASE)" -o wide
	kubectl -n "$(DOWNLOADER_NAMESPACE)" \
		get pvc dinosaur-downloader-state dinosaur-media-pvc

logs-downloader:
	kubectl -n "$(DOWNLOADER_NAMESPACE)" logs \
		deployment/"$(DOWNLOADER_RELEASE)" \
		--tail=100 -f

port-forward-downloader:
	kubectl -n "$(DOWNLOADER_NAMESPACE)" port-forward \
		svc/"$(DOWNLOADER_RELEASE)" \
		$(DOWNLOADER_LOCAL_PORT):8085 \
		--address 127.0.0.1
