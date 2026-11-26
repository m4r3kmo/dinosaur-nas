ARGOCD_NAMESPACE := argocd
ARGOCD_RELEASE := argocd
ARGOCD_DIR := infrastructure/argocd

.PHONY: help-argocd \
        template-argocd \
        deploy-argocd \
        status-argocd \
        logs-argocd \
        logs-argocd-controller

help-argocd:
	@echo ""
	@echo "Argo CD GitOps:"
	@echo "  make template-argocd - Render Helm templates"
	@echo "  make deploy-argocd   - Deploy Argo CD"
	@echo "  make status-argocd   - Argo CD overview"
	@echo "  make logs-argocd     - Follow server logs"
	@echo "  make logs-argocd-controller - Controller logs"

template-argocd:
	helm template $(ARGOCD_RELEASE) argo/argo-cd \
		--namespace $(ARGOCD_NAMESPACE) \
		--version $(ARGOCD_CHART_VERSION) \
		-f $(ARGOCD_DIR)/values.yaml

deploy-argocd:
	helm upgrade --install $(ARGOCD_RELEASE) argo/argo-cd \
		--namespace $(ARGOCD_NAMESPACE) \
		--create-namespace \
		--version $(ARGOCD_CHART_VERSION) \
		-f $(ARGOCD_DIR)/values.yaml \
		--wait \
		--timeout 10m
	kubectl apply -f $(ARGOCD_DIR)/certificate.yaml
	kubectl wait --for=condition=Ready \
		certificate/dinosaur-argocd \
		-n $(ARGOCD_NAMESPACE) --timeout=180s
	kubectl apply -f $(ARGOCD_DIR)/ingressroute.yaml

status-argocd:
	kubectl get pods,svc -n $(ARGOCD_NAMESPACE)
	kubectl get certificates -n $(ARGOCD_NAMESPACE)
	kubectl get ingressroute -n $(ARGOCD_NAMESPACE)
	kubectl get servicemonitors -n $(ARGOCD_NAMESPACE)
	kubectl get applications -n $(ARGOCD_NAMESPACE)

logs-argocd:
	kubectl logs -n $(ARGOCD_NAMESPACE) \
		deployment/argocd-server -f

logs-argocd-controller:
	kubectl logs -n $(ARGOCD_NAMESPACE) \
		statefulset/argocd-application-controller -f
