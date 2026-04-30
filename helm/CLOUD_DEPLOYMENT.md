# Cloud Deployment Guide

Deploy fintech data mesh to AWS, GCP, or Azure with cloud-specific optimizations.

---

## AWS EKS Deployment

### Prerequisites

```bash
# Install AWS CLI, eksctl, kubectl
brew install awscli eksctl kubectl

# Configure AWS credentials
aws configure
```

### Step 1: Create EKS Cluster

```bash
eksctl create cluster \
  --name fintech-mesh-prod \
  --region us-east-1 \
  --nodes 5 \
  --node-type m5.2xlarge \
  --with-oidc \
  --enable-ssm  # For secure pod access
```

### Step 2: Create IAM Roles for Workloads

```bash
# Spark role
aws iam create-role \
  --role-name EKS-Spark-Role \
  --assume-role-policy-document file://spark-trust-policy.json

# Attach S3 policy
aws iam attach-role-policy \
  --role-name EKS-Spark-Role \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess

# Create IRSA service account
kubectl create serviceaccount spark -n fintech-mesh
kubectl annotate serviceaccount spark \
  -n fintech-mesh \
  eks.amazonaws.com/role-arn=arn:aws:iam::ACCOUNT_ID:role/EKS-Spark-Role
```

### Step 3: Create S3 Bucket

```bash
aws s3 mb s3://fintech-mesh-warehouse --region us-east-1

# Enable versioning (for snapshots)
aws s3api put-bucket-versioning \
  --bucket fintech-mesh-warehouse \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket fintech-mesh-warehouse \
  --server-side-encryption-configuration '{"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}'
```

### Step 4: Deploy Fintech Mesh

```bash
# Update values file with your account ID and bucket name
sed -i 's/ACCOUNT_ID/YOUR_ACCOUNT_ID/g' helm/values-aws-eks.yaml
sed -i 's/fintech-mesh-warehouse/YOUR_BUCKET_NAME/g' helm/values-aws-eks.yaml

# Deploy
helm install fintech-mesh ./helm \
  -f helm/values-aws-eks.yaml \
  -n fintech-mesh \
  --create-namespace

# Verify deployment
kubectl get pods -n fintech-mesh
kubectl get svc -n fintech-mesh
```

### Step 5: Configure Load Balancer

```bash
# Create ALB
helm repo add aws-load-balancer-controller https://aws.github.io/eks-charts
helm install aws-load-balancer-controller aws-load-balancer-controller/aws-load-balancer-controller \
  -n kube-system

# Deploy ingress
kubectl apply -f manifests/aws-alb-ingress.yaml
```

### Monitoring

```bash
# View Prometheus metrics
kubectl port-forward svc/prometheus 9090:9090 -n fintech-mesh

# View Grafana dashboards
kubectl port-forward svc/grafana 3000:3000 -n fintech-mesh
```

### Cost Optimization (AWS)

```bash
# Use Spot instances for non-critical workloads
eksctl create nodegroup \
  --cluster fintech-mesh-prod \
  --spot \
  --node-type m5.2xlarge \
  --nodes 5

# Reserve instances for baseline
# (Configure in AWS Console or via Terraform)
```

### AWS-Specific Commands

```bash
# Check Spark logs
aws logs tail /aws/eks/fintech-mesh/spark

# Monitor costs
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost

# Backup S3
aws s3 sync s3://fintech-mesh-warehouse s3://backup-bucket/
```

---

## GCP GKE Deployment

### Prerequisites

```bash
# Install gcloud SDK, kubectl
brew install google-cloud-sdk kubectl

# Authenticate
gcloud auth login
gcloud config set project my-fintech-project
```

### Step 1: Create GKE Cluster

```bash
gcloud container clusters create fintech-mesh-prod \
  --zone us-central1-a \
  --num-nodes 5 \
  --machine-type n1-highmem-4 \
  --enable-autoscaling \
  --min-nodes 3 \
  --max-nodes 20 \
  --enable-workload-identity
```

### Step 2: Create Service Accounts (Workload Identity)

```bash
# Create Google service account
gcloud iam service-accounts create spark \
  --display-name="Spark service account"

# Grant Cloud Storage permissions
gcloud projects add-iam-policy-binding my-fintech-project \
  --member=serviceAccount:spark@my-fintech-project.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin

# Bind to Kubernetes service account
gcloud iam service-accounts add-iam-policy-binding \
  spark@my-fintech-project.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:my-fintech-project.svc.id.goog[fintech-mesh/spark]"

# Create K8s service account with annotation
kubectl create serviceaccount spark -n fintech-mesh
kubectl annotate serviceaccount spark \
  -n fintech-mesh \
  iam.gke.io/gcp-service-account=spark@my-fintech-project.iam.gserviceaccount.com
```

### Step 3: Create GCS Bucket

```bash
# Create bucket
gsutil mb -p my-fintech-project gs://fintech-mesh-warehouse

# Set lifecycle rule (delete old versions)
gsutil lifecycle set lifecycle.json gs://fintech-mesh-warehouse

# Enable versioning
gsutil versioning set on gs://fintech-mesh-warehouse
```

### Step 4: Deploy Fintech Mesh

```bash
# Update values
sed -i 's/my-fintech-project/YOUR_PROJECT_ID/g' helm/values-gcp-gke.yaml

# Deploy
helm install fintech-mesh ./helm \
  -f helm/values-gcp-gke.yaml \
  -n fintech-mesh \
  --create-namespace
```

### Step 5: Configure Cloud SQL

```bash
# Create Cloud SQL instance
gcloud sql instances create fintech-mesh-postgres \
  --database-version=POSTGRES_14 \
  --tier=db-custom-4-16384 \
  --region=us-central1

# Create database
gcloud sql databases create iceberg \
  --instance=fintech-mesh-postgres

# Create user
gcloud sql users create iceberg \
  --instance=fintech-mesh-postgres \
  --password=YOUR_PASSWORD
```

### GCP-Specific Commands

```bash
# Monitor costs
gcloud billing accounts list
gcloud compute instances describe fintech-mesh-prod --zone=us-central1-a

# View logs
gcloud logging read "resource.type=k8s_cluster" --limit 50

# Scale cluster
gcloud container clusters resize fintech-mesh-prod --num-nodes 10 --zone us-central1-a

# Export data to BigQuery
bq mk --dataset fintech_mesh_analytics
gsutil -m cp gs://fintech-mesh-warehouse/**/*.parquet gs://bigquery-datasets/
```

---

## Azure AKS Deployment

### Prerequisites

```bash
# Install Azure CLI, kubectl
brew install azure-cli kubectl

# Login
az login
az account set --subscription YOUR_SUBSCRIPTION_ID
```

### Step 1: Create AKS Cluster

```bash
# Create resource group
az group create \
  --name fintech-mesh-rg \
  --location eastus

# Create AKS cluster
az aks create \
  --resource-group fintech-mesh-rg \
  --name fintech-mesh-prod \
  --node-count 5 \
  --vm-set-type VirtualMachineScaleSets \
  --enable-managed-identity \
  --enable-aad \
  --network-plugin azure
```

### Step 2: Create Storage Account

```bash
# Create storage account
az storage account create \
  --name fintemeshstorage \
  --resource-group fintech-mesh-rg \
  --location eastus \
  --sku Premium_LRS

# Create container
az storage container create \
  --name warehouse \
  --account-name fintemeshstorage

# Get access key
az storage account keys list \
  --account-name fintemeshstorage \
  --resource-group fintech-mesh-rg
```

### Step 3: Create Database for PostgreSQL

```bash
# Create Azure Database for PostgreSQL
az postgres server create \
  --resource-group fintech-mesh-rg \
  --name fintech-mesh-postgres \
  --location eastus \
  --admin-user postgres \
  --admin-password YOUR_PASSWORD \
  --sku-name Standard_D4s_v3 \
  --storage-mb 524288

# Create database
az postgres db create \
  --resource-group fintech-mesh-rg \
  --server-name fintech-mesh-postgres \
  --name iceberg
```

### Step 4: Deploy Fintech Mesh

```bash
# Get cluster credentials
az aks get-credentials \
  --resource-group fintech-mesh-rg \
  --name fintech-mesh-prod

# Update values
sed -i 's/fintemeshstorage/YOUR_STORAGE_ACCOUNT/g' helm/values-azure-aks.yaml

# Deploy
helm install fintech-mesh ./helm \
  -f helm/values-azure-aks.yaml \
  -n fintech-mesh \
  --create-namespace
```

### Step 5: Create Application Gateway (Ingress)

```bash
# Deploy Application Gateway
helm repo add application-gateway https://appgwingress.blob.core.windows.net/helm/
helm install appgw-ingress-controller application-gateway/ingress-azure \
  -n kube-system
```

### Azure-Specific Commands

```bash
# Monitor costs
az costmanagement forecast create \
  --scope "/subscriptions/YOUR_SUBSCRIPTION_ID"

# View cluster logs
az aks show-location \
  --resource-group fintech-mesh-rg \
  --name fintech-mesh-prod

# Scale cluster
az aks scale \
  --resource-group fintech-mesh-rg \
  --name fintech-mesh-prod \
  --node-count 10

# Back up to Azure Backup
az backup vault create \
  --resource-group fintech-mesh-rg \
  --name fintech-mesh-recovery \
  --location eastus
```

---

## Multi-Cloud Deployment

### Architecture

```
                    ┌─────────────────┐
                    │  DNS (Route 53) │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
       ┌────▼────┐     ┌─────▼────┐   ┌─────▼────┐
       │ AWS EKS │     │ GCP GKE  │   │ Azure AKS│
       │ us-east │     │ us-cent. │   │ us-east  │
       └────┬────┘     └─────┬────┘   └─────┬────┘
            │                │                │
            └────────────────┼────────────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
       ┌────▼────┐     ┌─────▼────┐   ┌─────▼────┐
       │   S3    │     │   GCS    │   │  Blob    │
       │ Storage │     │ Storage  │   │ Storage  │
       └─────────┘     └──────────┘   └──────────┘
```

### Federated Data Mesh

```bash
# Deploy to all three clouds
./scripts/deploy-multi-cloud.sh

# Verify replication
kubectl get pods -A | grep fintech-mesh

# Test data consistency
./scripts/test-consistency.sh
```

---

## Monitoring Across Clouds

```bash
# Unified metrics dashboard
kubectl apply -f manifests/multi-cloud-prometheus.yaml

# Federated Prometheus (scrapes all clouds)
helm install prometheus-fed ./helm/prometheus-federated \
  -f helm/values-federated-monitoring.yaml

# Access unified Grafana
kubectl port-forward svc/grafana-federated 3000:3000
# Dashboard shows metrics from all 3 clouds
```

---

## Cost Comparison

```
Monthly cost for baseline (5 nodes, 50GB storage):

AWS EKS:
├── Compute (5 × m5.2xlarge): $2,000
├── Storage (S3): $1,200
└── Total: $3,200

GCP GKE:
├── Compute (5 × n1-highmem-4): $1,800
├── Storage (GCS): $1,000
└── Total: $2,800

Azure AKS:
├── Compute (5 × Standard_D4s_v3): $1,900
├── Storage (Blob): $1,100
└── Total: $3,000
```

---

## Recommendations

| Cloud | Best For | Reason |
|-------|----------|--------|
| **AWS** | Existing AWS infrastructure, multi-region | Mature services, cost predictable |
| **GCP** | Data science, BigQuery integration | Native BigQuery, lower compute cost |
| **Azure** | Microsoft ecosystem, Hybrid Cloud | Azure DevOps, seamless AD integration |

For multi-cloud: Use AWS as primary, GCP/Azure as failover/secondary regions.
