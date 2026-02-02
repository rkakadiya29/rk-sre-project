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
command: /opt/homebrew/share/google-cloud-sdk/bin/gke-gcloud-auth-plugin #in kubeconfig

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
kubectl apply -f operator/deploy/cr.yaml

kopf run operator/src/operator.py --verbose  

kubectl create clusterrolebinding cluster-admin-binding \
  --clusterrole=cluster-admin \
  --user=$(gcloud config get-value account)

# deploy test apps
kubectl apply -f test_apps/app1/app1.yaml
kubectl apply -k test_apps/app2/bookinfo-example/kustomize/
kubectl patch crd noderefreshes.stable.rk.ai -p '{"metadata":{"finalizers":null}}' --type=merge

kubectl patch namespace simple-web -p '{"spec": {"finalizers": []}}' --type=merge

kubectl get noderefresh rk-node-refresh -w -o jsonpath='{.status}'
kubectl get pods -A --field-selector spec.nodeName=gke-gke-k8s-cluster1-default-pool-c3dadcb4-xc19

kubectl patch noderefresh rk-node-refresh-cycle -p '{"metadata":{"finalizers":null}}' --type=merge


# gcloud commands
gcloud container node-pools describe default-pool \
    --cluster k8s-cluster1 \
    --zone us-central1-a

gcloud container node-pools update default-pool \
    --cluster k8s-cluster1 \
    --zone us-central1-a \
    --disk-size 25 \
    --node-labels tier=worker
kubectl uncordon -l tier=worker
gcloud container clusters resize k8s-cluster1 \
    --node-pool default-pool \
    --num-nodes 1 \
    --zone us-central1-a

gcloud container node-pools delete default-pool \
    --cluster k8s-cluster1 \
    --zone us-central1-a

gcloud container node-pools create default-pool \
    --cluster k8s-cluster1 \
    --zone us-central1-a \
    --num-nodes 1 \
    --machine-type e2-small \
    --disk-size 30 \
    --node-labels generation=v1,tier=worker \
    --scopes "https://www.googleapis.com/auth/cloud-platform"

gcloud container node-pools list \
    --cluster k8s-cluster1 \
    --zone us-central1-a \
    --project project-c668633a-e9a8-4b7e-8a0