# -----------------------------------------------------------------------------
# Makefile for Python-based Kubernetes Operator with Kind Cluster Support
# -----------------------------------------------------------------------------
# Image name and tag (change according to your registry/project)
IMG ?= my-operator:latest
# Kubernetes namespace for deployment
NAMESPACE ?= default
# Kind cluster name
KIND_CLUSTER ?= operator-dev
.PHONY: all build push load deploy deploy-crd deploy-cr deploy-operator \
       undeploy undeploy-crd undeploy-cr undeploy-operator \
       test kind-cluster kind-delete
# -----------------------------------------------------------------------------
# Build and Push
# -----------------------------------------------------------------------------
# Build the operator Docker image
build:
docker build -t $(IMG) -f Dockerfile .
# Push the image to container registry
push:
docker push $(IMG)
# Load the image into Kind (for local testing without pushing to registry)
kind-load: build
kind load docker-image $(IMG) --name $(KIND_CLUSTER)
# -----------------------------------------------------------------------------
# Kind Cluster Management
# -----------------------------------------------------------------------------
# Create a Kind cluster for local testing
kind-cluster:
kind create cluster --name $(KIND_CLUSTER)
# Delete the Kind cluster
kind-delete:
kind delete cluster --name $(KIND_CLUSTER)
# -----------------------------------------------------------------------------
# Deploy (applies manifests into cluster)
# -----------------------------------------------------------------------------
# Deploy everything: CRDs, Operator, and CRs
deploy: deploy-crd deploy-operator deploy-cr
# Deploy only CRDs (CustomResourceDefinitions)
deploy-crd:
kubectl apply -f deploy/crd/
# Deploy only Operator (Deployment, RBAC, Service)
deploy-operator:
kubectl apply -f deploy/operator/ -n $(NAMESPACE)
# Deploy only CRs (Custom Resources = actual test configs)
deploy-cr:
kubectl apply -f deploy/cr/ -n $(NAMESPACE)
# -----------------------------------------------------------------------------
# Undeploy (removes manifests from cluster)
# -----------------------------------------------------------------------------
# Remove everything: CRs, Operator, and CRDs
undeploy: undeploy-cr undeploy-operator undeploy-crd
# Remove only CRs
undeploy-cr:
kubectl delete -f deploy/cr/ -n $(NAMESPACE) --ignore-not-found
# Remove only Operator
undeploy-operator:
kubectl delete -f deploy/operator/ -n $(NAMESPACE) --ignore-not-found
# Remove only CRDs
undeploy-crd:
kubectl delete -f deploy/crd/ --ignore-not-found
# -----------------------------------------------------------------------------
# Testing
# -----------------------------------------------------------------------------
# Run local unit tests for the operator
test:
pytest -v tests/
