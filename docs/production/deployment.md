# Production Deployment Guide

Deploying the fintech data mesh to Kubernetes (EKS, GKE, AKS).

---

## Quick Start: Docker Compose (Local)

For development and testing:

```bash
cd chakraview-fintech-data-mesh
docker-compose up -d

# Verify services
docker-compose logs -f

# Access ports
Kafka: localhost:9092
Zookeeper: localhost:2181
Schema Registry: localhost:8081
Iceberg REST Catalog: localhost:8181
MinIO: localhost:9000
Prometheus: localhost:9090
Grafana: localhost:3000
OPA: localhost:8181
Elasticsearch: localhost:9200
Discovery Portal: localhost:8000
```

---

## Kubernetes Deployment (Production)

### Prerequisites

```bash
# EKS
eksctl create cluster --name fintech-mesh --region us-east-1 --nodes 5

# GKE
gcloud container clusters create fintech-mesh --num-nodes 5 --region us-east-1

# AKS
az aks create --name fintech-mesh --resource-group myresourcegroup --node-count 5
```

### Helm Charts

Deploy using Helm (charts/ directory):

```bash
# Add Helm repositories
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add confluentinc https://confluentinc.github.io/cp-helm-charts
helm repo update

# Deploy Kafka stack
helm install kafka confluentinc/cp-helm-charts \
  --set cp-zookeeper.enabled=true \
  --set cp-kafka.brokers=3 \
  --set cp-schema-registry.enabled=true

# Deploy Iceberg catalog
helm install iceberg-catalog ./helm/iceberg-catalog \
  --set image.repository=apache/iceberg-catalog \
  --set replicas=3

# Deploy MinIO (S3-compatible storage)
helm install minio bitnami/minio \
  --set accessKey=minioadmin \
  --set secretKey=minioadmin \
  --set persistence.size=500Gi

# Deploy Spark
helm install spark ./helm/spark \
  --set executors=5 \
  --set executor-cores=4 \
  --set executor-memory=8Gi

# Deploy OPA
helm install opa ./helm/opa \
  --set replicas=2

# Deploy Prometheus + Grafana
helm install monitoring prometheus-community/kube-prometheus-stack \
  --set grafana.adminPassword=admin

# Deploy Discovery Portal
helm install discovery-portal ./helm/discovery-portal \
  --set replicas=3
```

### Configuration

Create values files for environments:

```yaml
# helm/values-prod.yaml
kafka:
  replicas: 5
  retention_ms: 604800000  # 7 days
  min_insync_replicas: 2

iceberg:
  warehouse: s3://fintech-mesh-warehouse
  catalog_type: rest
  replicas: 3

spark:
  executors: 10
  executor_cores: 8
  executor_memory: 16Gi

prometheus:
  retention: 30d
  storage_size: 100Gi

grafana:
  replicas: 2

opa:
  replicas: 3
  policy_sync_interval: 60s
```

Deploy:
```bash
helm upgrade --install fintech-mesh ./helm \
  -f helm/values-prod.yaml
```

---

## Domain Ingest Job Deployment

Deploy Spark Structured Streaming jobs as Kubernetes Pods:

```yaml
# kubernetes/transaction-ingest-job.yaml
apiVersion: v1
kind: Pod
metadata:
  name: transaction-ingest-job
  namespace: fintech-mesh
spec:
  containers:
  - name: spark-driver
    image: apache/spark:3.3.0
    command: ["python", "-m", "domains.transactions.ingest.ingest_job"]
    env:
    - name: KAFKA_BROKERS
      value: "kafka:9092"
    - name: CATALOG_URI
      value: "http://iceberg-catalog:8181"
    - name: WAREHOUSE
      value: "s3://fintech-mesh-warehouse"
    resources:
      requests:
        memory: "8Gi"
        cpu: "4"
      limits:
        memory: "16Gi"
        cpu: "8"
    restartPolicy: Always
```

Deploy all domains:
```bash
kubectl apply -f kubernetes/transaction-ingest-job.yaml
kubectl apply -f kubernetes/account-ingest-job.yaml
kubectl apply -f kubernetes/risk-compliance-ingest-job.yaml
kubectl apply -f kubernetes/counterparty-ingest-job.yaml
kubectl apply -f kubernetes/market-data-ingest-job.yaml
```

---

## Storage Configuration

### S3 (AWS)

```yaml
# Iceberg configuration
spark.sql.catalog.rest.type: rest
spark.sql.catalog.rest.uri: http://iceberg-catalog:8181
spark.sql.catalog.rest.warehouse: s3://fintech-mesh-warehouse/
spark.hadoop.fs.s3a.access.key: ${AWS_ACCESS_KEY_ID}
spark.hadoop.fs.s3a.secret.key: ${AWS_SECRET_ACCESS_KEY}
spark.hadoop.fs.s3a.endpoint: https://s3.us-east-1.amazonaws.com
```

### GCS (Google Cloud)

```yaml
spark.sql.catalog.rest.warehouse: gs://fintech-mesh-warehouse/
spark.hadoop.google.cloud.auth.type: APPLICATION_DEFAULT
spark.hadoop.google.cloud.project.id: my-project
```

### MinIO (On-Premises or Local)

```yaml
spark.sql.catalog.rest.warehouse: s3://fintech-mesh-warehouse/
spark.hadoop.fs.s3a.endpoint: http://minio:9000
spark.hadoop.fs.s3a.access.key: minioadmin
spark.hadoop.fs.s3a.secret.key: minioadmin
spark.hadoop.fs.s3a.path.style.access: true
```

---

## Networking & Security

### Network Policies

```yaml
# kubernetes/network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: fintech-mesh-policies
  namespace: fintech-mesh
spec:
  # Default deny ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: discovery-portal
    ports:
    - protocol: TCP
      port: 8000

  # Allow Kafka only from ingest jobs
  - from:
    - podSelector:
        matchLabels:
          type: ingest-job
    ports:
    - protocol: TCP
      port: 9092

  # Allow OPA from all pods (for policy evaluation)
  - from:
    - podSelector: {}
    ports:
    - protocol: TCP
      port: 8181
```

### RBAC (Role-Based Access Control)

```yaml
# kubernetes/rbac.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: ingest-job-role
  namespace: fintech-mesh
rules:
- apiGroups: [""]
  resources: ["pods", "logs"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["configmaps", "secrets"]
  resourceNames: ["kafka-brokers", "aws-credentials"]
  verbs: ["get"]
```

---

## Monitoring & Alerting

### Deploy Prometheus ServiceMonitor

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: fintech-mesh-monitoring
  namespace: fintech-mesh
spec:
  selector:
    matchLabels:
      app: fintech-mesh
  endpoints:
  - port: metrics
    interval: 30s
```

### Grafana Dashboards

Dashboards are deployed via ConfigMap:

```bash
kubectl create configmap grafana-dashboards \
  --from-file=platform/observability/grafana_dashboard.json \
  -n fintech-mesh
```

---

## Backup & Disaster Recovery

### Iceberg Snapshots

Iceberg maintains immutable snapshots. Retention policy controls deletion:

```python
# Automatic cleanup (configured per domain)
retention_policy:
  transactions: 7 years
  accounts: 3 years
  market_data: 1 year
```

### Kafka Topic Backups

Kafka topics are replicated across 3 brokers (HA). For long-term archive:

```bash
# Export Kafka topic to S3 (daily)
kafka-mirror-maker \
  --consumer.config=source.conf \
  --producer.config=s3.conf \
  --whitelist="market-transactions-raw"
```

### Iceberg Table Backups

Time-travel enables point-in-time recovery:

```sql
-- Restore to state from 2 hours ago
SELECT * FROM transactions.raw_transactions 
  FOR SYSTEM_TIME AS OF timestamp_sub(now(), INTERVAL 2 hours);
```

---

## Scaling Considerations

### Horizontal Scaling

```yaml
# Increase replicas
kubectl scale deployment discovery-portal --replicas=5

# Increase Kafka partitions
kafka-topics.sh --bootstrap-server kafka:9092 \
  --alter --topic market-transactions-raw --partitions 20

# Scale Spark executors (edit Helm values)
helm upgrade fintech-mesh ./helm \
  --set spark.executors=20
```

### Vertical Scaling

```yaml
# Increase memory/CPU per pod
kubectl set resources deployment transaction-ingest-job \
  --limits=cpu=16,memory=32Gi \
  --requests=cpu=8,memory=16Gi
```

---

## Troubleshooting

### Check Service Health

```bash
# Kafka broker health
kubectl logs -f pod/kafka-0 -n fintech-mesh

# Iceberg catalog logs
kubectl logs -f pod/iceberg-catalog-0 -n fintech-mesh

# Ingest job logs
kubectl logs -f pod/transaction-ingest-job -n fintech-mesh

# Check metrics
curl http://localhost:9090/api/v1/query?query=up
```

### Common Issues

**1. Ingest job lag > 5 minutes**
```bash
# Check Kafka lag
kubectl exec -it pod/kafka-0 -- \
  kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --group transaction-ingest-consumer \
  --describe

# Scale Spark if needed
kubectl set resources deployment spark-executor \
  --limits=cpu=16,memory=32Gi
```

**2. OPA policy evaluation slow**
```bash
# Check OPA logs
kubectl logs -f pod/opa-0 -n fintech-mesh

# Verify policy loaded
curl http://localhost:8181/v1/data/authz
```

**3. Iceberg write timeouts**
```bash
# Check MinIO/S3 connectivity
kubectl exec -it pod/spark-driver -- \
  aws s3api head-bucket --bucket fintech-mesh-warehouse

# Increase timeout in Spark config
spark.sql.iceberg.commit.timeout.ms: 600000
```

---

## Next

- **[Scaling Guide](scaling.md)** — Performance tuning for production workloads
- **[Trade-offs](trade-offs.md)** — Architecture decisions and alternatives
