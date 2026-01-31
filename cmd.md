--------------k8s commands-----------
kubectl get pods -A -o wide --sort-by=.spec.nodeName
kubectl get pods -A --field-selector spec.nodeName=k8s-cluster1-worker1
kubectl get pods -l tier=worker -o wide -n kube-system
kubectl get pods -A -o wide | grep -E 'k8s-cluster1-worker'
kubectl get nodes --show-labels | grep node-generation=gen2

kubectl delete pods -n kube-system -l app=kindnet

# installing gcloud sdk
gcloud components install gke-gcloud-auth-plugin
# update ~/.kube/config (if req.)
export USE_GKE_GCLOUD_AUTH_PLUGIN=True
gcloud container clusters get-credentials k8s-cluster1 --zone us-central1-a

# gcloud
gcloud auth login
gcloud config set project project-c668633a-e9a8-4b7e-8a0
gcloud container clusters create k8s-cluster1 \
    --num-nodes=1 \
    --machine-type=e2-medium \
    --zone=us-central1-a \
    --node-labels=tier=worker
gcloud container clusters get-credentials k8s-cluster1 --zone us-central1-a
gcloud services enable container.googleapis.com
gcloud auth application-default login

# running operator
source kopf-env/bin/activate

kubectl apply -f operator/deploy/crd.yaml
kubectl config current-context
command: /opt/homebrew/share/google-cloud-sdk/bin/gke-gcloud-auth-plugin
kopf run operator/src/operator.py --verbose --context gke_project-c668633a-e9a8-4b7e-8a0_us-central1-a_k8s-cluster1
kubectl apply -f operator/deploy/cr.yaml


kubectl create clusterrolebinding cluster-admin-binding \
  --clusterrole=cluster-admin \
  --user=$(gcloud config get-value account)