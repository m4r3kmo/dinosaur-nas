# ---------------------------------------------------------------------------
# Dinosaur Monitoring
# ---------------------------------------------------------------------------

MONITORING_NAMESPACE := monitoring
MONITORING_RELEASE := monitoring
MONITORING_CHART := oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack
MONITORING_VALUES := infrastructure/monitoring/values.yaml

.PHONY: help-monitoring
.PHONY: template-monitoring deploy-monitoring
.PHONY: status-monitoring storage-monitoring
.PHONY: logs-prometheus logs-grafana

help-monitoring:
	@echo ""
	@echo "Dinosaur Monitoring:"
	@echo "  make storage-monitoring  - Apply monitoring storage"
	@echo "  make template-monitoring - Render Helm templates"
	@echo "  make deploy-monitoring   - Deploy monitoring stack"
	@echo "  make status-monitoring   - Monitoring overview"
	@echo "  make logs-prometheus     - Follow Prometheus logs"
	@echo "  make logs-grafana        - Follow Grafana logs"

storage-monitoring: storage-verify
	mountpoint -q /mnt/disk1
	kubectl apply -f infrastructure/monitoring/storage.yaml
	kubectl apply -f infrastructure/monitoring/grafana-pvc.yaml

template-monitoring:
	helm template "$(MONITORING_RELEASE)" \
		"$(MONITORING_CHART)" \
		--version "$(KUBE_PROMETHEUS_STACK_VERSION)" \
		--namespace "$(MONITORING_NAMESPACE)" \
		-f "$(MONITORING_VALUES)"

deploy-monitoring: storage-monitoring
	kubectl -n "$(MONITORING_NAMESPACE)" get secret grafana-admin
	helm upgrade --install "$(MONITORING_RELEASE)" \
		"$(MONITORING_CHART)" \
		--version "$(KUBE_PROMETHEUS_STACK_VERSION)" \
		--namespace "$(MONITORING_NAMESPACE)" \
		-f "$(MONITORING_VALUES)" \
		--wait \
		--wait-for-jobs \
		--timeout 15m

status-monitoring:
	kubectl -n "$(MONITORING_NAMESPACE)" \
		get deployment,statefulset,daemonset,pods,svc,pvc -o wide
	kubectl get pv -l 'component in (prometheus,grafana,alertmanager)'
	kubectl -n "$(MONITORING_NAMESPACE)" get prometheus,alertmanager

logs-prometheus:
	kubectl -n "$(MONITORING_NAMESPACE)" logs \
		-l app.kubernetes.io/name=prometheus \
		-c prometheus --tail=100 -f

logs-grafana:
	kubectl -n "$(MONITORING_NAMESPACE)" logs \
		-l app.kubernetes.io/name=grafana \
		-c grafana --tail=100 -f

# ---------------------------------------------------------------------------
# SMART Exporter
# ---------------------------------------------------------------------------

SMARTCTL_CHART := oci://ghcr.io/prometheus-community/charts/prometheus-smartctl-exporter
SMARTCTL_VALUES := infrastructure/monitoring/exporters/smartctl/values.yaml

.PHONY: help-smartctl template-smartctl deploy-smartctl
.PHONY: status-smartctl logs-smartctl

help-smartctl:
	@echo ""
	@echo "SMART Exporter:"
	@echo "  make template-smartctl - Render Helm templates"
	@echo "  make deploy-smartctl   - Deploy SMART Exporter"
	@echo "  make status-smartctl   - Exporter status"
	@echo "  make logs-smartctl     - Follow exporter logs"

template-smartctl:
	helm template smartctl-exporter \
		"$(SMARTCTL_CHART)" \
		--version "$(SMARTCTL_EXPORTER_VERSION)" \
		--namespace monitoring \
		-f "$(SMARTCTL_VALUES)"

deploy-smartctl:
	helm upgrade --install smartctl-exporter \
		"$(SMARTCTL_CHART)" \
		--version "$(SMARTCTL_EXPORTER_VERSION)" \
		--namespace monitoring \
		-f "$(SMARTCTL_VALUES)" \
		--wait \
		--timeout 5m

status-smartctl:
	kubectl -n monitoring get daemonset,pods,svc,servicemonitor \
		-l app.kubernetes.io/instance=smartctl-exporter

logs-smartctl:
	kubectl -n monitoring logs \
		-l app.kubernetes.io/instance=smartctl-exporter \
		--tail=100 -f

.PHONY: deploy-smartctl-rules

deploy-smartctl-rules:
	kubectl apply -f infrastructure/monitoring/exporters/smartctl/rules.yaml

# ---------------------------------------------------------------------------
# Grafana dashboards
# ---------------------------------------------------------------------------

.PHONY: deploy-dashboards status-dashboards

deploy-dashboards:
	kubectl apply -k infrastructure/monitoring/dashboards/

status-dashboards:
	kubectl -n monitoring get configmap -l grafana_dashboard=1

# ---------------------------------------------------------------------------
# NVIDIA GPU Metrics
# ---------------------------------------------------------------------------

GPU_METRICS_DIR := infrastructure/monitoring/exporters/nvidia

.PHONY: deploy-gpu-metrics status-gpu-metrics

deploy-gpu-metrics:
	sudo install -d -m 0755 /usr/local/lib/dinosaur-nas
	sudo install -m 0644 $(GPU_METRICS_DIR)/collect.py /usr/local/lib/dinosaur-nas/nvidia-collect.py
	sudo install -m 0644 $(GPU_METRICS_DIR)/dinosaur-gpu-metrics.service /etc/systemd/system/
	sudo install -m 0644 $(GPU_METRICS_DIR)/dinosaur-gpu-metrics.timer /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl start dinosaur-gpu-metrics.service
	sudo systemctl enable --now dinosaur-gpu-metrics.timer

status-gpu-metrics:
	systemctl status dinosaur-gpu-metrics.timer --no-pager
	cat /run/dinosaur-metrics/nvidia.prom

# ---------------------------------------------------------------------------
# Blackbox Exporter
# ---------------------------------------------------------------------------

BLACKBOX_CHART := oci://ghcr.io/prometheus-community/charts/prometheus-blackbox-exporter
BLACKBOX_VALUES := infrastructure/monitoring/exporters/blackbox/values.yaml

.PHONY: help-blackbox template-blackbox deploy-blackbox
.PHONY: status-blackbox logs-blackbox

help-blackbox:
	@echo ""
	@echo "Blackbox Exporter:"
	@echo "  make template-blackbox - Render Helm templates"
	@echo "  make deploy-blackbox   - Deploy Blackbox Exporter"
	@echo "  make status-blackbox   - Exporter status"
	@echo "  make logs-blackbox     - Follow exporter logs"

template-blackbox:
	helm template blackbox-exporter \
		"$(BLACKBOX_CHART)" \
		--version "$(BLACKBOX_EXPORTER_VERSION)" \
		--namespace monitoring \
		-f "$(BLACKBOX_VALUES)"

deploy-blackbox:
	kubectl -n monitoring get configmap dinosaur-root-ca
	helm upgrade --install blackbox-exporter \
		"$(BLACKBOX_CHART)" \
		--version "$(BLACKBOX_EXPORTER_VERSION)" \
		--namespace monitoring \
		-f "$(BLACKBOX_VALUES)" \
		--wait \
		--timeout 5m

status-blackbox:
	kubectl -n monitoring get deployment,pods,svc,servicemonitor \
		-l app.kubernetes.io/instance=blackbox-exporter

logs-blackbox:
	kubectl -n monitoring logs \
		deployment/dinosaur-blackbox --tail=100 -f

.PHONY: deploy-blackbox-rules status-blackbox-rules

deploy-blackbox-rules:
	kubectl apply --dry-run=server -f infrastructure/monitoring/exporters/blackbox/rules.yaml
	kubectl apply -f infrastructure/monitoring/exporters/blackbox/rules.yaml

status-blackbox-rules:
	kubectl -n monitoring get prometheusrule dinosaur-blackbox-rules

# ---------------------------------------------------------------------------
# PKI Metrics
# ---------------------------------------------------------------------------

PKI_METRICS_DIR := infrastructure/monitoring/exporters/pki
PKI_SOURCE_DIR := $(HOME)/.config/dinosaur-nas/pki

.PHONY: help-pki-metrics deploy-pki-metrics
.PHONY: status-pki-metrics sync-pki-metrics

help-pki-metrics:
	@echo ""
	@echo "PKI Metrics:"
	@echo "  make deploy-pki-metrics - Install PKI collector"
	@echo "  make status-pki-metrics - Show PKI metrics"
	@echo "  make sync-pki-metrics   - Update public CA certificates"

sync-pki-metrics:
	sudo install -d -m 0755 /etc/dinosaur-nas/pki
	sudo install -m 0644 "$(PKI_SOURCE_DIR)/dinosaur-ca.crt" /etc/dinosaur-nas/pki/
	sudo install -m 0644 "$(PKI_SOURCE_DIR)/dinosaur-intermediate-ca.crt" /etc/dinosaur-nas/pki/

deploy-pki-metrics: sync-pki-metrics
	sudo install -d -m 0755 /usr/local/lib/dinosaur-nas
	sudo install -m 0644 $(PKI_METRICS_DIR)/collect.py /usr/local/lib/dinosaur-nas/pki-collect.py
	sudo install -m 0644 $(PKI_METRICS_DIR)/dinosaur-pki-metrics.service /etc/systemd/system/
	sudo install -m 0644 $(PKI_METRICS_DIR)/dinosaur-pki-metrics.timer /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl start dinosaur-pki-metrics.service
	sudo systemctl enable --now dinosaur-pki-metrics.timer

status-pki-metrics:
	systemctl status dinosaur-pki-metrics.timer --no-pager
	cat /run/dinosaur-metrics/pki.prom

.PHONY: deploy-pki-rules status-pki-rules

deploy-pki-rules:
	kubectl apply --dry-run=server -f infrastructure/monitoring/exporters/pki/rules.yaml
	kubectl apply -f infrastructure/monitoring/exporters/pki/rules.yaml

status-pki-rules:
	kubectl -n monitoring get prometheusrule dinosaur-pki-rules
