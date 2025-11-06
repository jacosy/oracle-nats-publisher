# Kubernetes Deployment Guide

## Overview

This guide covers deploying the Oracle NATS Publisher to Kubernetes with secure credential management using HashiCorp Vault.

## Architecture

```
┌─────────────────────────────────────────────────┐
│              Kubernetes Cluster                  │
│                                                  │
│  ┌────────────────────────────────────────┐    │
│  │  Namespace: oracle-nats-publisher      │    │
│  │                                         │    │
│  │  ┌──────────────────────┐              │    │
│  │  │ Pod: oracle-nats-    │              │    │
│  │  │      publisher       │              │    │
│  │  │                      │              │    │
│  │  │ ┌─────────────────┐ │              │    │
│  │  │ │ Vault Agent     │ │              │    │
│  │  │ │ (Sidecar)       │ │              │    │
│  │  │ │ - Injects creds │ │              │    │
│  │  │ └─────────────────┘ │              │    │
│  │  │                      │              │    │
│  │  │ ┌─────────────────┐ │              │    │
│  │  │ │ App Container   │ │              │    │
│  │  │ │ - Reads creds   │ │              │    │
│  │  │ │ - Polls Oracle  │ │              │    │
│  │  │ │ - Publishes NATS│ │              │    │
│  │  │ └─────────────────┘ │              │    │
│  │  └──────────────────────┘              │    │
│  │           │  │  │                      │    │
│  │           │  │  └──────────────┐       │    │
│  │           │  │                 │       │    │
│  └───────────│──│─────────────────│───────┘    │
│              │  │                 │            │
│              │  │                 │            │
│      ┌───────▼──▼──────┐   ┌─────▼──────┐    │
│      │ ConfigMap       │   │ Vault      │    │
│      │ (non-sensitive) │   │ (secrets)  │    │
│      └─────────────────┘   └────────────┘    │
│                                                │
└────────────┬──────────────┬──────────────┬────┘
             │              │              │
             ▼              ▼              ▼
        ┌────────┐    ┌──────────┐   ┌────────┐
        │ Oracle │    │ MariaDB  │   │ NATS   │
        └────────┘    └──────────┘   └────────┘
```

## Prerequisites

### Required

1. **Kubernetes Cluster** (v1.20+)
2. **kubectl** configured
3. **Docker** for building images
4. **HashiCorp Vault** (for secure credential management)
5. **Vault Agent Injector** installed in cluster

### Optional

- **Kustomize** (built into kubectl v1.14+)
- **Helm** (if using Helm charts)
- **Private container registry**

## Deployment Options

### Option 1: Using HashiCorp Vault (Recommended for Production)

#### Step 1: Install Vault (if not already installed)

```bash
# Using Helm
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update

helm install vault hashicorp/vault \
  --namespace vault \
  --create-namespace \
  --set "injector.enabled=true"

# Wait for Vault to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=vault -n vault --timeout=300s
```

#### Step 2: Initialize and Unseal Vault

```bash
# Initialize Vault (SAVE THE KEYS!)
kubectl exec -n vault vault-0 -- vault operator init

# Unseal Vault (use keys from init)
kubectl exec -n vault vault-0 -- vault operator unseal <unseal-key-1>
kubectl exec -n vault vault-0 -- vault operator unseal <unseal-key-2>
kubectl exec -n vault vault-0 -- vault operator unseal <unseal-key-3>

# Login to Vault
kubectl exec -n vault vault-0 -- vault login <root-token>
```

#### Step 3: Configure Vault for the Application

```bash
# Set environment variables
export VAULT_ADDR="http://vault.vault.svc.cluster.local:8200"
export VAULT_TOKEN="<your-root-token>"

# Run the setup script
chmod +x k8s/vault-setup.sh
./k8s/vault-setup.sh
```

#### Step 4: Update Credentials in Vault

```bash
# Oracle credentials
vault kv put secret/oracle-nats-publisher/oracle \
    username="real_oracle_user" \
    password="real_oracle_password" \
    dsn="oracle-prod.example.com:1521/PROD"

# MariaDB credentials
vault kv put secret/oracle-nats-publisher/mariadb \
    username="real_mariadb_user" \
    password="real_mariadb_password"

# NATS credentials (if using auth)
vault kv put secret/oracle-nats-publisher/nats \
    username="real_nats_user" \
    password="real_nats_password"
```

#### Step 5: Deploy the Application

```bash
# Create namespace and service account
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/serviceaccount.yaml

# Deploy ConfigMap (non-sensitive config)
kubectl apply -f k8s/configmap.yaml

# Deploy with Vault integration
kubectl apply -f k8s/vault-integration.yaml
```

#### Step 6: Verify Deployment

```bash
# Check pod status
kubectl get pods -n oracle-nats-publisher

# Check pod logs
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher -f

# Check Vault agent logs
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher -c vault-agent

# Verify secrets were injected
kubectl exec -n oracle-nats-publisher -it <pod-name> -- ls -la /vault/secrets/
```

---

### Option 2: Using Kubernetes Secrets (Not Recommended for Production)

#### Step 1: Create Namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

#### Step 2: Create Secrets

**Option A: From command line**
```bash
kubectl create secret generic oracle-nats-secrets \
  --from-literal=oracle-username='your_user' \
  --from-literal=oracle-password='your_password' \
  --from-literal=oracle-dsn='host:1521/ORCL' \
  --from-literal=mariadb-username='your_user' \
  --from-literal=mariadb-password='your_password' \
  --namespace oracle-nats-publisher
```

**Option B: From file (update k8s/secret.yaml first)**
```bash
# Base64 encode your credentials
echo -n 'your_username' | base64
echo -n 'your_password' | base64

# Update k8s/secret.yaml with encoded values
# Then apply
kubectl apply -f k8s/secret.yaml
```

#### Step 3: Deploy Application

```bash
kubectl apply -f k8s/serviceaccount.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
```

---

### Option 3: Using Kustomize

```bash
# Update kustomization.yaml with your image
vim k8s/kustomization.yaml

# Deploy everything
kubectl apply -k k8s/

# Or with custom overlay
kubectl apply -k k8s/overlays/production/
```

## Configuration

### ConfigMap (Non-Sensitive)

Edit `k8s/configmap.yaml` to configure:

- Database hosts and ports
- NATS servers
- Polling intervals
- Batch sizes
- Log levels

```yaml
data:
  MARIADB_HOST: "mariadb.database.svc.cluster.local"
  NATS_SERVERS: "nats://nats.messaging.svc.cluster.local:4222"
  POLL_INTERVAL: "60"
  BATCH_SIZE: "100"
  LOG_LEVEL: "INFO"
```

### Secrets (Sensitive)

**Never commit secrets to Git!**

Credentials should be stored in:
- ✅ HashiCorp Vault (recommended)
- ✅ Kubernetes secrets (encrypted at rest)
- ✅ Cloud provider secret managers (AWS Secrets Manager, GCP Secret Manager, Azure Key Vault)

## Resource Management

### Resource Requests and Limits

Current settings in `deployment.yaml`:

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

Adjust based on your workload:

| Workload Size | Memory Request | Memory Limit | CPU Request | CPU Limit |
|---------------|----------------|--------------|-------------|-----------|
| Small (< 1K records/min) | 128Mi | 256Mi | 100m | 250m |
| Medium (1K-10K records/min) | 256Mi | 512Mi | 250m | 500m |
| Large (10K-100K records/min) | 512Mi | 1Gi | 500m | 1000m |
| XLarge (> 100K records/min) | 1Gi | 2Gi | 1000m | 2000m |

### Horizontal Pod Autoscaling (HPA)

**NOT RECOMMENDED** for this application because:
- Only one instance should poll to avoid duplicate processing
- Use `replicas: 1` with `strategy: Recreate`

If you need higher throughput:
- Increase batch size
- Increase resources (vertical scaling)
- Partition data by time ranges or event types

## Health Checks

### Liveness Probe

Checks if the application is alive (restarts pod if failing):

```yaml
livenessProbe:
  exec:
    command:
      - /bin/sh
      - -c
      - ps aux | grep '[p]ython src/main.py' || exit 1
  initialDelaySeconds: 60
  periodSeconds: 30
  failureThreshold: 3
```

### Readiness Probe

Checks if the application is ready to serve traffic:

```yaml
readinessProbe:
  exec:
    command:
      - /bin/sh
      - -c
      - ps aux | grep '[p]ython src/main.py' || exit 1
  initialDelaySeconds: 30
  periodSeconds: 10
  failureThreshold: 3
```

**Future Enhancement**: Add HTTP health check endpoint.

## Graceful Shutdown

The deployment is configured for graceful shutdown:

1. **terminationGracePeriodSeconds: 90**
   - Should be > poll_interval (60s default)
   - Allows current cycle to complete

2. **preStop Hook**
   ```yaml
   lifecycle:
     preStop:
       exec:
         command:
           - /bin/sh
           - -c
           - kill -TERM 1; sleep 10
   ```

3. **Application Handling**
   - Signal handler sets `running = False`
   - Current cycle completes
   - Graceful cleanup of all connections

## Monitoring and Logging

### Viewing Logs

```bash
# Follow logs
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher -f

# Last 100 lines
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher --tail=100

# Logs from specific time
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher --since=1h

# Previous pod logs (after restart)
kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher --previous
```

### Key Log Messages to Monitor

```
✅ "Connected to NATS"
✅ "Initialization complete"
✅ "Cycle completed: X records published"
✅ "Successfully published all X messages"

⚠️  "No new records"
⚠️  "Cycle failed, will retry"

❌ "Failed to connect"
❌ "Connection timed out"
❌ "Failed to publish"
```

### Integration with Logging Systems

**Fluentd/Fluent Bit**:
```bash
# Logs are automatically collected if logging daemonset is running
kubectl get daemonset -n kube-system
```

**ELK Stack**:
- Logs forwarded to Elasticsearch
- View in Kibana

**Cloud Provider Logging**:
- GKE: Logs appear in Cloud Logging
- EKS: Logs sent to CloudWatch
- AKS: Logs sent to Azure Monitor

## Security

### Security Contexts

The deployment uses restrictive security contexts:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true  # (false for Vault integration)
  capabilities:
    drop:
      - ALL
```

### Network Policies (Optional)

Create network policies to restrict traffic:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: oracle-nats-publisher-netpol
  namespace: oracle-nats-publisher
spec:
  podSelector:
    matchLabels:
      app: oracle-nats-publisher
  policyTypes:
    - Egress
  egress:
    - to:  # Oracle
        - namespaceSelector:
            matchLabels:
              name: database
      ports:
        - protocol: TCP
          port: 1521
    - to:  # MariaDB
        - namespaceSelector:
            matchLabels:
              name: database
      ports:
        - protocol: TCP
          port: 3306
    - to:  # NATS
        - namespaceSelector:
            matchLabels:
              name: messaging
      ports:
        - protocol: TCP
          port: 4222
    - to:  # DNS
        - namespaceSelector:
            matchLabels:
              name: kube-system
      ports:
        - protocol: UDP
          port: 53
```

## Troubleshooting

### Pod Not Starting

```bash
# Check pod status
kubectl describe pod -n oracle-nats-publisher <pod-name>

# Check events
kubectl get events -n oracle-nats-publisher --sort-by='.lastTimestamp'

# Check logs
kubectl logs -n oracle-nats-publisher <pod-name>
```

### Common Issues

#### 1. ImagePullBackOff

**Cause**: Cannot pull container image

**Solution**:
```bash
# Check image exists
docker pull oracle-nats-publisher:v7.0

# Add image pull secret if using private registry
kubectl create secret docker-registry registry-credentials \
  --docker-server=<your-registry> \
  --docker-username=<username> \
  --docker-password=<password> \
  --namespace oracle-nats-publisher

# Update deployment to use secret
# imagePullSecrets:
#   - name: registry-credentials
```

#### 2. CrashLoopBackOff

**Cause**: Application crashing on startup

**Solution**:
```bash
# Check application logs
kubectl logs -n oracle-nats-publisher <pod-name>

# Common causes:
# - Database connection failures
# - NATS connection failures
# - Missing credentials
# - Configuration errors
```

#### 3. Vault Secrets Not Injected

**Cause**: Vault agent not running or misconfigured

**Solution**:
```bash
# Check Vault agent logs
kubectl logs -n oracle-nats-publisher <pod-name> -c vault-agent

# Verify Vault configuration
vault read auth/kubernetes/role/oracle-nats-publisher

# Check service account
kubectl get sa oracle-nats-publisher-sa -n oracle-nats-publisher
```

#### 4. Connection Timeout

**Cause**: Cannot reach Oracle/MariaDB/NATS

**Solution**:
```bash
# Test connectivity from pod
kubectl exec -n oracle-nats-publisher <pod-name> -it -- /bin/sh

# Test Oracle
nc -zv oracle-host 1521

# Test MariaDB
nc -zv mariadb-host 3306

# Test NATS
nc -zv nats-host 4222

# Check network policies
kubectl get networkpolicies -n oracle-nats-publisher
```

## Updating the Deployment

### Update Image

```bash
# Update image tag
kubectl set image deployment/oracle-nats-publisher \
  publisher=oracle-nats-publisher:v7.1 \
  -n oracle-nats-publisher

# Check rollout status
kubectl rollout status deployment/oracle-nats-publisher -n oracle-nats-publisher
```

### Update Configuration

```bash
# Edit ConfigMap
kubectl edit configmap oracle-nats-config -n oracle-nats-publisher

# Restart deployment to pick up changes
kubectl rollout restart deployment/oracle-nats-publisher -n oracle-nats-publisher
```

### Update Secrets (Vault)

```bash
# Update secret in Vault
vault kv put secret/oracle-nats-publisher/oracle \
    username="new_user" \
    password="new_password"

# Restart pod to get new secrets
kubectl delete pod -n oracle-nats-publisher -l app=oracle-nats-publisher
```

## Cleanup

### Remove Deployment

```bash
# Delete application
kubectl delete -f k8s/vault-integration.yaml
# or
kubectl delete -f k8s/deployment.yaml

# Delete ConfigMap and Secrets
kubectl delete -f k8s/configmap.yaml
kubectl delete -f k8s/secret.yaml

# Delete service account
kubectl delete -f k8s/serviceaccount.yaml

# Delete namespace (removes everything)
kubectl delete namespace oracle-nats-publisher
```

### Remove Vault Configuration

```bash
# Delete secrets from Vault
vault kv delete secret/oracle-nats-publisher/oracle
vault kv delete secret/oracle-nats-publisher/mariadb
vault kv delete secret/oracle-nats-publisher/nats

# Delete Vault role
vault delete auth/kubernetes/role/oracle-nats-publisher

# Delete Vault policy
vault policy delete oracle-nats-publisher
```

## Production Checklist

Before deploying to production:

- [ ] Vault installed and configured
- [ ] Real credentials stored in Vault (not examples)
- [ ] Resource limits configured appropriately
- [ ] Liveness and readiness probes tested
- [ ] Graceful shutdown tested (terminationGracePeriodSeconds)
- [ ] Logging integrated with monitoring system
- [ ] Network policies configured (if using)
- [ ] Security contexts reviewed
- [ ] Backup and restore procedures documented
- [ ] Runbooks created for common issues
- [ ] On-call team trained

## Support

For issues:
1. Check logs: `kubectl logs -n oracle-nats-publisher -l app=oracle-nats-publisher`
2. Check events: `kubectl get events -n oracle-nats-publisher`
3. Review this documentation
4. Check application documentation: `README.md`, `GRACEFUL_SHUTDOWN.md`, `CONNECTION_RACE_CONDITIONS.md`
