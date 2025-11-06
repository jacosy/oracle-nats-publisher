# Oracle NATS Publisher V7

A Python application that polls Oracle database for transaction log events and publishes them to NATS JetStream using **async/await** for high-throughput batch publishing, with ETL tracking in MariaDB.

## Features

- **3-Layer Architecture**: Clean separation between db_clients, repositories, and services
- **Async Batch Publishing**: High-throughput concurrent message publishing to NATS
- **ETL Tracking**: Progress tracking in MariaDB with success/failure monitoring
- **Retry Logic**: Automatic retry with exponential backoff for failed messages
- **Connection Pooling**: Efficient database connection management
- **Graceful Shutdown**: Proper cleanup of all resources

## Prerequisites

- Python 3.7+
- Oracle Database (with spc.TXLOG_EVENTS table)
- MariaDB/MySQL (with ETL_PRMREC tracking table)
- NATS Server with JetStream enabled

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd oracle-nats-publisher
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

**Option A: Environment variables (recommended)**

```bash
cp .env.example .env
# Edit .env with your settings

export ORACLE_USER="your_username"
export ORACLE_PASSWORD="your_password"
export ORACLE_DSN="localhost:1521/ORCL"
export MARIADB_HOST="localhost"
export MARIADB_PASSWORD="your_password"
export NATS_SERVERS="nats://localhost:4222"
```

**Option B: Config file**

```bash
cp config/config.yaml.example config/config.yaml
# Edit config/config.yaml with your settings
```

⚠️ **SECURITY**: Never commit credentials! Use environment variables in production.

### 3. Run

```bash
python src/main.py
```

## Architecture

### 3-Layer Design

```
main.py (Orchestration)
    ↓
services/ (Layer 3: Business Logic)
    ↓
repositories/ (Layer 2: Data Access Patterns)
    ↓
db_clients/ (Layer 1: Pure CRUD)
```

**Layer 1: db_clients/** - Pure CRUD operations
- `oracle_db_client.py`: Oracle connection and query execution
- `mariadb_db_client.py`: MariaDB connection and query execution
- `nats_client.py`: NATS JetStream async batch publishing

**Layer 2: repositories/** - Data access patterns
- `oracle_repository.py`: Business queries for Oracle
- `mariadb_repository.py`: ETL tracking queries

**Layer 3: services/** - Business logic
- `polling_service.py`: Orchestrates poll → publish → track workflow

**Publishers/** - External integrations
- `txlog_event_publisher.py`: Formats and publishes TxLog events to NATS

### Publishing Flow

1. Get last successful time from MariaDB tracking
2. Fetch new events from Oracle since that time
3. Format events and **async batch publish** to NATS
4. Update MariaDB tracking on success

## Configuration

Configuration priority (highest to lowest):
1. **Environment variables**
2. **config/config.yaml**
3. **Default values**

### Key Settings

- **oracle_db**: Oracle connection (username, password, dsn)
- **mariadb**: MariaDB connection for ETL tracking
- **nats**: NATS server connection settings
- **publisher**: Program name, polling interval, batch size, retries
- **logging**: Log level and format

See `config/config.yaml.example` for all options.

## Database Setup

### MariaDB ETL Tracking Table

```sql
CREATE TABLE ETL_PRMREC (
    PROGRAM_NAME VARCHAR(100) PRIMARY KEY,
    LAST_SUCCESSFUL_TIME DATETIME,
    LAST_RUN_TIME DATETIME,
    STATUS VARCHAR(50),
    RECORDS_PROCESSED INT DEFAULT 0,
    ERROR_MESSAGE TEXT,
    CREATED_AT DATETIME DEFAULT CURRENT_TIMESTAMP,
    UPDATED_AT DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

## Security Best Practices

### ⚠️ Credentials Management

**DO NOT commit credentials to version control!**

- ✅ Use environment variables for all secrets
- ✅ Use `.env` files locally (excluded by `.gitignore`)
- ✅ Use Kubernetes secrets in production
- ✅ Use secret management tools (Vault, AWS Secrets Manager)
- ❌ Never put passwords in `config.yaml` if committing to Git

### Files

- `config/config.yaml` is in `.gitignore` - DO NOT commit
- Use `config/config.yaml.example` as a template
- Use `.env.example` as environment variable template

## Docker

```bash
docker build -t oracle-nats-publisher .

docker run -d \
  --name oracle-nats-publisher \
  -e ORACLE_USER="your_user" \
  -e ORACLE_PASSWORD="your_password" \
  -e ORACLE_DSN="host:1521/service" \
  -e MARIADB_HOST="mariadb" \
  -e MARIADB_PASSWORD="your_password" \
  -e NATS_SERVERS="nats://nats:4222" \
  oracle-nats-publisher
```

## Kubernetes

```bash
kubectl apply -f k8s/
```

## Troubleshooting

### Connection Issues

**Oracle:** Check ORACLE_DSN format: `host:port/service_name`
**MariaDB:** Verify MARIADB_HOST and database exists
**NATS:** Check NATS_SERVERS URL and JetStream enabled

### Publishing Issues

- Check last_successful_time in ETL_PRMREC table
- Review retry configuration (max_retries)
- Check batch_size setting

## Version

**V7.0** - Async Architecture with High-Throughput Publishing
