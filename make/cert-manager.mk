# ---------------------------------------------------------------------------
# Cert-manager
# ---------------------------------------------------------------------------

CERT_MANAGER_NAMESPACE := cert-manager
CERT_MANAGER_CHART := oci://quay.io/jetstack/charts/cert-manager
CERT_MANAGER_VALUES := infrastructure/cert-manager/values.yaml

.PHONY: help-cert-manager
.PHONY: template-cert-manager deploy-cert-manager
.PHONY: status-cert-manager logs-cert-manager
.PHONY: test-cert-manager clean-cert-manager-test

help-cert-manager:
	@echo ""
	@echo "Certificate management:"
	@echo "  make template-cert-manager - Render Helm templates"
	@echo "  make deploy-cert-manager   - Install cert-manager"
	@echo "  make status-cert-manager   - Certificate overview"
	@echo "  make logs-cert-manager     - Follow controller logs"
	@echo "  make test-cert-manager     - Test certificate issuance"
	@echo "  make clean-cert-manager-test - Remove smoke test"

template-cert-manager:
	helm template cert-manager \
		"$(CERT_MANAGER_CHART)" \
		--version "$(CERT_MANAGER_VERSION)" \
		--namespace "$(CERT_MANAGER_NAMESPACE)" \
		-f "$(CERT_MANAGER_VALUES)"

deploy-cert-manager:
	helm upgrade --install cert-manager \
		"$(CERT_MANAGER_CHART)" \
		--version "$(CERT_MANAGER_VERSION)" \
		--namespace "$(CERT_MANAGER_NAMESPACE)" \
		--create-namespace \
		-f "$(CERT_MANAGER_VALUES)" \
		--wait \
		--wait-for-jobs \
		--timeout 5m

status-cert-manager:
	kubectl -n "$(CERT_MANAGER_NAMESPACE)" \
		get deployment,pods,svc
	kubectl get clusterissuers
	kubectl get issuers,certificates,certificaterequests -A

logs-cert-manager:
	kubectl -n "$(CERT_MANAGER_NAMESPACE)" logs \
		deployment/cert-manager --tail=100 -f

test-cert-manager:
	kubectl apply -f infrastructure/cert-manager/smoke-test.yaml
	kubectl -n dinosaur-pki-test wait \
		--for=condition=Ready \
		certificate/cert-manager-smoke-test \
		--timeout=180s
	kubectl -n dinosaur-pki-test get \
		issuer,certificate,certificaterequest

clean-cert-manager-test:
	kubectl delete -f infrastructure/cert-manager/smoke-test.yaml

# ---------------------------------------------------------------------------
# Dinosaur PKI
# ---------------------------------------------------------------------------

PKI_NAMESPACE := media
PKI_CERTIFICATE := dinosaur-wildcard
PKI_TLS_SECRET := dinosaur-wildcard-managed-tls
PKI_CA_FILE := $(HOME)/.config/dinosaur-nas/pki/dinosaur-ca.crt
PKI_HOSTS := download.dinosaur.lan jellyfin.dinosaur.lan
PKI_IP := 192.168.100.50

.PHONY: help-pki deploy-pki status-pki renew-pki verify-pki

help-pki:
	@echo ""
	@echo "Dinosaur PKI:"
	@echo "  make deploy-pki - Apply ClusterIssuer and Certificate"
	@echo "  make status-pki - Certificate status and renewal time"
	@echo "  make renew-pki  - Force certificate renewal"
	@echo "  make verify-pki - Verify live HTTPS certificates"

deploy-pki:
	kubectl -n cert-manager get secret dinosaur-intermediate-ca
	kubectl apply -f infrastructure/cert-manager/cluster-issuer.yaml
	kubectl wait --for=condition=Ready clusterissuer/dinosaur-ca --timeout=120s
	kubectl apply -f infrastructure/cert-manager/wildcard-certificate.yaml
	kubectl -n $(PKI_NAMESPACE) wait --for=condition=Ready certificate/$(PKI_CERTIFICATE) --timeout=180s

status-pki:
	kubectl get clusterissuer dinosaur-ca
	cmctl status certificate $(PKI_CERTIFICATE) -n $(PKI_NAMESPACE)
	kubectl -n $(PKI_NAMESPACE) get certificate $(PKI_CERTIFICATE) \
		-o jsonpath='Renewal: {.status.renewalTime}{"\n"}'

renew-pki:
	cmctl renew $(PKI_CERTIFICATE) --namespace $(PKI_NAMESPACE)

verify-pki:
	@bash -e -o pipefail -c '\
	expected=$$(kubectl -n "$(PKI_NAMESPACE)" get secret "$(PKI_TLS_SECRET)" \
		-o jsonpath="{.data.tls\.crt}" | base64 -d | openssl x509 -noout -fingerprint -sha256); \
	for host in $(PKI_HOSTS); do \
		echo "=== $$host ==="; \
		cert=$$(openssl s_client \
			-connect "$(PKI_IP):443" \
			-servername "$$host" \
			-CAfile "$(PKI_CA_FILE)" \
			-verify_hostname "$$host" \
			-verify_return_error </dev/null 2>/dev/null); \
		printf "%s\n" "$$cert" | openssl x509 -noout -subject -issuer -dates -serial; \
		actual=$$(printf "%s\n" "$$cert" | openssl x509 -noout -fingerprint -sha256); \
		test "$$actual" = "$$expected" || { echo "ERROR: Certificate mismatch"; exit 1; }; \
		echo "Verification: OK"; \
		echo; \
	done'
