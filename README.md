# Oracle NATS Publisher - V7

Fetches data from Oracle database and publishes to NATS, with ETL tracking in MariaDB.

## Architecture

```
main.py (Orchestration)
    ↓
services/etl_service.py (Business Logic)
    ↓                              ↓
repositories/                  repositories/
oracle_repository.py          mariadb_repository.py
    ↓                              ↓
db_clients/                    db_clients/
oracle_db_client.py           mariadb_db_client.py
```

## Folder Structure

```
src/
├── main.py                    # Application entry point
├── db_clients/                # Layer 1: Pure CRUD
├── repositories/              # Layer 2: Data access patterns
├── services/                  # Layer 3: Business logic
├── publishers/                # External integrations
└── config/                    # Configuration
```

## Quick Start

### Local Development

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run application
python src/main.py
```

### Configuration

Edit `config/config.yaml` or use environment variables:

```bash
export ORACLE_USER="your_user"
export ORACLE_PASSWORD="your_password"
export ORACLE_DSN="host:1521/SERVICE"
export MARIADB_HOST="mariadb-host"
export MARIADB_PASSWORD="your_password"
export NATS_SERVERS="nats://nats-host:4222"
```

## Features

- ✅ Layered architecture (CRUD → Queries → Logic)
- ✅ Organized by folders (clear layer boundaries)
- ✅ Synchronous code (no async complexity)
- ✅ Kubernetes-ready (ConfigMap/Secret support)
- ✅ Dual database (Oracle source, MariaDB tracking)
- ✅ NATS publishing with batching

## Version

**V7.0** - Layered Architecture with Folder Organization
