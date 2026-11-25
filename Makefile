.DEFAULT_GOAL := help

.PHONY: help status nodes pods services releases gpu

help:
	@echo "Dinosaur NAS Infrastructure"
	@echo ""
	@echo "make status    - Cluster overview"
	@echo "make nodes     - Kubernetes nodes"
	@echo "make pods      - Kubernetes pods"
	@echo "make services  - Kubernetes services"
	@echo "make releases  - Helm releases"
	@echo "make gpu       - NVIDIA GPU status"

status: nodes pods services releases

nodes:
	kubectl get nodes -o wide

pods:
	kubectl get pods -A

services:
	kubectl get svc -A

releases:
	helm list -A

gpu:
	nvidia-smi
