#!/bin/bash
CLUSTER_NAME="k8s-cluster1"
REGION="us-central1"

gcloud container clusters create $CLUSTER_NAME \
    --zone us-central1-a \
    --num-nodes 2 \
    --machine-type "e2-small" \
    --spot \
    --enable-ip-alias \
    --no-enable-cloud-logging
    --node-labels=tier=worker  # <--- This labels the actual worker nodes

# Get credentials to start using kubectl
gcloud container clusters get-credentials $CLUSTER_NAME --region $REGION