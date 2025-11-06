#!/bin/bash
# HashiCorp Vault Setup Script for Oracle NATS Publisher
# This script configures Vault to store and manage credentials

set -e

# Configuration
VAULT_ADDR="${VAULT_ADDR:-http://vault.vault.svc.cluster.local:8200}"
VAULT_TOKEN="${VAULT_TOKEN:-}"
NAMESPACE="oracle-nats-publisher"
APP_NAME="oracle-nats-publisher"

echo "=== HashiCorp Vault Setup for Oracle NATS Publisher ==="
echo "Vault Address: $VAULT_ADDR"
echo "Namespace: $NAMESPACE"
echo ""

# Check if VAULT_TOKEN is set
if [ -z "$VAULT_TOKEN" ]; then
    echo "Error: VAULT_TOKEN environment variable is not set"
    echo "Please set it with: export VAULT_TOKEN=<your_token>"
    exit 1
fi

export VAULT_ADDR

echo "Step 1: Enable KV v2 secrets engine (if not already enabled)"
vault secrets enable -path=secret kv-v2 2>/dev/null || echo "  KV v2 already enabled"

echo ""
echo "Step 2: Create secrets in Vault"

# Oracle credentials
echo "  Creating Oracle credentials..."
vault kv put secret/oracle-nats-publisher/oracle \
    username="your_oracle_username" \
    password="your_oracle_password" \
    dsn="oracle-host:1521/ORCL"

# MariaDB credentials
echo "  Creating MariaDB credentials..."
vault kv put secret/oracle-nats-publisher/mariadb \
    username="your_mariadb_username" \
    password="your_mariadb_password"

# NATS credentials (optional)
echo "  Creating NATS credentials..."
vault kv put secret/oracle-nats-publisher/nats \
    username="your_nats_username" \
    password="your_nats_password"

echo ""
echo "Step 3: Verify secrets"
echo "  Oracle:"
vault kv get secret/oracle-nats-publisher/oracle
echo ""
echo "  MariaDB:"
vault kv get secret/oracle-nats-publisher/mariadb
echo ""
echo "  NATS:"
vault kv get secret/oracle-nats-publisher/nats

echo ""
echo "Step 4: Enable Kubernetes auth method (if not already enabled)"
vault auth enable kubernetes 2>/dev/null || echo "  Kubernetes auth already enabled"

echo ""
echo "Step 5: Configure Kubernetes auth"
# Get Kubernetes CA cert and host
K8S_HOST="https://kubernetes.default.svc.cluster.local:443"

echo "  Configuring Kubernetes auth with cluster..."
vault write auth/kubernetes/config \
    kubernetes_host="$K8S_HOST"

echo ""
echo "Step 6: Create Vault policy for the application"
vault policy write oracle-nats-publisher - <<EOF
# Policy for Oracle NATS Publisher
path "secret/data/oracle-nats-publisher/*" {
  capabilities = ["read", "list"]
}
EOF

echo ""
echo "Step 7: Create Vault role for Kubernetes service account"
vault write auth/kubernetes/role/oracle-nats-publisher \
    bound_service_account_names=oracle-nats-publisher-sa \
    bound_service_account_namespaces=$NAMESPACE \
    policies=oracle-nats-publisher \
    ttl=24h

echo ""
echo "=== Vault Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Update credentials in Vault with real values:"
echo "   vault kv put secret/oracle-nats-publisher/oracle username='real_user' password='real_pass' dsn='real_host:1521/ORCL'"
echo ""
echo "2. Deploy the application:"
echo "   kubectl apply -f k8s/namespace.yaml"
echo "   kubectl apply -f k8s/serviceaccount.yaml"
echo "   kubectl apply -f k8s/configmap.yaml"
echo "   kubectl apply -f k8s/vault-integration.yaml"
echo ""
echo "3. Verify the deployment:"
echo "   kubectl get pods -n $NAMESPACE"
echo "   kubectl logs -n $NAMESPACE -l app=oracle-nats-publisher"
