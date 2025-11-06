# Kubernetes Deployment Guide

This guide provides instructions for deploying the Oracle NATS Publisher to Kubernetes with HashiCorp Vault for secure credential management.

## Prerequisites

- Kubernetes cluster (v1.20+)
- kubectl configured to access your cluster
- HashiCorp Vault installed in the cluster (or external Vault accessible from the cluster)
- Vault Agent Injector installed (part of Vault Helm chart)
- Docker registry access to push/pull application images

## Architecture Overview

The deployment uses the following components:

1. **Namespace**: Isolated namespace for the application
2. **ServiceAccount**: Kubernetes service account with Vault authentication
3. **ConfigMap**: Non-sensitive configuration (polling intervals, NATS endpoints, etc.)
4. **Vault Secrets**: Sensitive credentials stored in Vault and injected via sidecar
5. **Deployment**: Application deployment with security best practices

## Security Features

- **Vault Integration**: All database credentials stored in Vault, never in K8s manifests
- **Non-root User**: Application runs as non-root user (UID 1000)
- **Read-only Root Filesystem**: Container filesystem is read-only for security
- **Security Context**: Pod and container security contexts enforce least privilege
- **No Privilege Escalation**: Prevents privilege escalation attacks
- **Resource Limits**: CPU and memory limits prevent resource exhaustion

## Step 1: Setup HashiCorp Vault

### 1.1 Install Vault (if not already installed)

```bash
# Add HashiCorp Helm repository
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update

# Install Vault with Agent Injector
helm install vault hashicorp/vault \
  --namespace vault \
  --create-namespace \
  --set "injector.enabled=true" \
  --set "server.dev.enabled=true"
```

**Note**: The above uses dev mode for testing. For production, use proper Vault configuration with persistent storage.

### 1.2 Configure Kubernetes Authentication

```bash
# Enable Kubernetes auth method in Vault
kubectl exec -n vault vault-0 -- vault auth enable kubernetes

# Configure Kubernetes auth
kubectl exec -n vault vault-0 -- vault write auth/kubernetes/config \
  kubernetes_host="https://kubernetes.default.svc:443"

# Create a policy for the application
kubectl exec -n vault vault-0 -- vault policy write oracle-nats-publisher - <<EOF
path "secret/data/oracle-nats-publisher/*" {
  capabilities = ["read", "list"]
}
EOF

# Create a role for the application
kubectl exec -n vault vault-0 -- vault write auth/kubernetes/role/oracle-nats-publisher \
  bound_service_account_names=oracle-nats-publisher \
  bound_service_account_namespaces=oracle-nats-publisher \
  policies=oracle-nats-publisher \
  ttl=24h
```

### 1.3 Store Secrets in Vault

```bash
# Enable KV v2 secrets engine (if not already enabled)
kubectl exec -n vault vault-0 -- vault secrets enable -path=secret kv-v2

# Store Oracle DB credentials
kubectl exec -n vault vault-0 -- vault kv put secret/oracle-nats-publisher/oracle-db \
  username="your_oracle_username" \
  password="your_oracle_password" \
  host="oracle.example.com" \
  port="1521" \
  service_name="ORCL"

# Store MariaDB credentials
kubectl exec -n vault vault-0 -- vault kv put secret/oracle-nats-publisher/mariadb \
  username="your_mariadb_username" \
  password="your_mariadb_password" \
  host="mariadb.example.com" \
  port="3306" \
  database="etl_tracking"

# Store NATS credentials (if authentication is enabled)
kubectl exec -n vault vault-0 -- vault kv put secret/oracle-nats-publisher/nats \
  username="nats_user" \
  password="nats_password"
```

### 1.4 Verify Secrets

```bash
# Verify Oracle credentials
kubectl exec -n vault vault-0 -- vault kv get secret/oracle-nats-publisher/oracle-db

# Verify MariaDB credentials
kubectl exec -n vault vault-0 -- vault kv get secret/oracle-nats-publisher/mariadb

# Verify NATS credentials
kubectl exec -n vault vault-0 -- vault kv get secret/oracle-nats-publisher/nats
```

## Step 2: Build and Push Docker Image

```bash
# Build the Docker image
docker build -t your-registry.com/oracle-nats-publisher:latest .

# Push to your registry
docker push your-registry.com/oracle-nats-publisher:latest
```

**Note**: Update the image reference in `04-deployment.yaml` to match your registry.

## Step 3: Configure the Deployment

### 3.1 Update ConfigMap (if needed)

Edit `k8s/03-configmap.yaml` to adjust non-sensitive configuration:

- NATS server endpoints
- Polling interval
- Batch size
- Log level
- etc.

### 3.2 Update Deployment Image

Edit `k8s/04-deployment.yaml` to use your Docker image:

```yaml
containers:
- name: oracle-nats-publisher
  image: your-registry.com/oracle-nats-publisher:latest  # Update this
```

## Step 4: Deploy to Kubernetes

```bash
# Apply all manifests in order
kubectl apply -f k8s/01-namespace.yaml
kubectl apply -f k8s/02-vault-secret.yaml
kubectl apply -f k8s/03-configmap.yaml
kubectl apply -f k8s/04-deployment.yaml

# Or apply all at once
kubectl apply -f k8s/
```

## Step 5: Verify Deployment

### 5.1 Check Pod Status

```bash
# Check if pods are running
kubectl get pods -n oracle-nats-publisher

# Expected output:
# NAME                                    READY   STATUS    RESTARTS   AGE
# oracle-nats-publisher-xxxxxxxxxx-xxxxx  2/2     Running   0          1m
```

**Note**: You should see 2/2 containers ready (application + Vault Agent sidecar).

### 5.2 Check Vault Agent Injection

```bash
# Describe the pod to see Vault annotations
kubectl describe pod -n oracle-nats-publisher -l app=oracle-nats-publisher

# Check if Vault secrets are injected
kubectl exec -n oracle-nats-publisher -c oracle-nats-publisher \
  $(kubectl get pod -n oracle-nats-publisher -l app=oracle-nats-publisher -o jsonpath='{.items[0].metadata.name}') \
  -- ls -la /vault/secrets/
```

### 5.3 Check Application Logs

```bash
# View application logs
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher -c oracle-nats-publisher --tail=100 -f

# View Vault Agent logs
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher -c vault-agent --tail=100 -f
```

## Step 6: Monitor the Application

### View Application Status

```bash
# Check deployment status
kubectl get deployment -n oracle-nats-publisher

# Check pod events
kubectl get events -n oracle-nats-publisher --sort-by='.lastTimestamp'

# Check resource usage
kubectl top pod -n oracle-nats-publisher
```

### Access Application Logs

```bash
# Stream logs
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher -c oracle-nats-publisher -f

# View recent logs
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher -c oracle-nats-publisher --tail=500
```

## Troubleshooting

### Pod Not Starting

```bash
# Check pod events
kubectl describe pod -n oracle-nats-publisher -l app=oracle-nats-publisher

# Check init container logs
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher -c vault-init
```

### Vault Authentication Issues

```bash
# Check Vault Agent logs
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher -c vault-agent

# Verify Vault role configuration
kubectl exec -n vault vault-0 -- vault read auth/kubernetes/role/oracle-nats-publisher

# Verify service account exists
kubectl get sa oracle-nats-publisher -n oracle-nats-publisher
```

### Database Connection Issues

```bash
# Check if credentials are properly injected
kubectl exec -n oracle-nats-publisher -c oracle-nats-publisher \
  $(kubectl get pod -n oracle-nats-publisher -l app=oracle-nats-publisher -o jsonpath='{.items[0].metadata.name}') \
  -- cat /vault/secrets/oracle

# Check application logs for connection errors
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher -c oracle-nats-publisher | grep -i error
```

### NATS Connection Issues

```bash
# Check NATS endpoint configuration
kubectl get configmap oracle-nats-publisher-config -n oracle-nats-publisher -o yaml

# Test NATS connectivity from pod
kubectl exec -n oracle-nats-publisher -c oracle-nats-publisher \
  $(kubectl get pod -n oracle-nats-publisher -l app=oracle-nats-publisher -o jsonpath='{.items[0].metadata.name}') \
  -- nc -zv nats.nats-system.svc.cluster.local 4222
```

## Updating the Application

### Update Configuration

```bash
# Edit ConfigMap
kubectl edit configmap oracle-nats-publisher-config -n oracle-nats-publisher

# Restart pods to pick up new configuration
kubectl rollout restart deployment/oracle-nats-publisher -n oracle-nats-publisher
```

### Update Secrets in Vault

```bash
# Update Oracle credentials
kubectl exec -n vault vault-0 -- vault kv put secret/oracle-nats-publisher/oracle-db \
  username="new_username" \
  password="new_password" \
  host="oracle.example.com" \
  port="1521" \
  service_name="ORCL"

# Restart pods to pick up new secrets
kubectl rollout restart deployment/oracle-nats-publisher -n oracle-nats-publisher
```

### Update Application Image

```bash
# Build and push new image
docker build -t your-registry.com/oracle-nats-publisher:v2 .
docker push your-registry.com/oracle-nats-publisher:v2

# Update deployment
kubectl set image deployment/oracle-nats-publisher \
  oracle-nats-publisher=your-registry.com/oracle-nats-publisher:v2 \
  -n oracle-nats-publisher

# Or edit deployment directly
kubectl edit deployment oracle-nats-publisher -n oracle-nats-publisher
```

## Scaling

This application is designed to run as a single instance due to its polling nature. However, if you need to process multiple data sources:

```bash
# Scale up (only if processing different data sources)
kubectl scale deployment/oracle-nats-publisher --replicas=3 -n oracle-nats-publisher

# Scale down
kubectl scale deployment/oracle-nats-publisher --replicas=1 -n oracle-nats-publisher
```

**Warning**: Running multiple replicas polling the same Oracle table may cause duplicate processing unless you implement proper distributed locking.

## Cleanup

```bash
# Delete all resources
kubectl delete -f k8s/

# Or delete namespace (deletes everything in it)
kubectl delete namespace oracle-nats-publisher
```

## Production Considerations

1. **High Availability Vault**: Use Vault in HA mode with proper storage backend (Consul, etcd)
2. **Image Pull Secrets**: If using private registry, create ImagePullSecrets
3. **Network Policies**: Implement NetworkPolicies to restrict pod-to-pod communication
4. **Resource Quotas**: Set ResourceQuotas for the namespace
5. **Monitoring**: Integrate with Prometheus/Grafana for monitoring
6. **Logging**: Use centralized logging (ELK, Loki, etc.)
7. **Backup**: Implement backup strategy for MariaDB tracking database
8. **Disaster Recovery**: Document and test DR procedures
9. **Secret Rotation**: Implement automated secret rotation
10. **Pod Disruption Budgets**: Define PodDisruptionBudgets for high availability

## Environment Variables Reference

The following environment variables are sourced from Vault:

| Variable | Source | Description |
|----------|--------|-------------|
| `ORACLE_USER` | Vault: oracle-db | Oracle database username |
| `ORACLE_PASSWORD` | Vault: oracle-db | Oracle database password |
| `ORACLE_HOST` | Vault: oracle-db | Oracle database host |
| `MARIADB_HOST` | Vault: mariadb | MariaDB host |
| `MARIADB_PORT` | Vault: mariadb | MariaDB port |
| `MARIADB_DATABASE` | Vault: mariadb | MariaDB database name |
| `MARIADB_USER` | Vault: mariadb | MariaDB username |
| `MARIADB_PASSWORD` | Vault: mariadb | MariaDB password |
| `NATS_USER` | Vault: nats | NATS username (optional) |
| `NATS_PASSWORD` | Vault: nats | NATS password (optional) |

The following environment variables are sourced from ConfigMap:

| Variable | ConfigMap Key | Default | Description |
|----------|---------------|---------|-------------|
| `NATS_SERVERS` | NATS_SERVERS | nats://nats:4222 | NATS server URL(s) |
| `POLL_INTERVAL` | POLL_INTERVAL | 60 | Polling interval in seconds |
| `BATCH_SIZE` | BATCH_SIZE | 100 | Batch size for publishing |
| `MAX_RECORDS_PER_RUN` | MAX_RECORDS_PER_RUN | 10000 | Max records per polling cycle |
| `LOG_LEVEL` | LOG_LEVEL | INFO | Logging level |

## Support

For issues or questions:
- Check application logs: `kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher -c oracle-nats-publisher`
- Check Vault Agent logs: `kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher -c vault-agent`
- Review Vault configuration and policies
- Verify network connectivity to databases and NATS
