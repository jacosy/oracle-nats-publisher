# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Oracle NATS Publisher V7 - A synchronous Python application that polls Oracle database for transaction log events and publishes them to NATS JetStream, with ETL tracking in MariaDB.

## Development Commands

### Setup
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running
```bash
# Run the application
python src/main.py
```

### Configuration
Edit `config/config.yaml` or use environment variables:
- `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_DSN` - Oracle connection
- `MARIADB_HOST`, `MARIADB_PASSWORD` - MariaDB connection
- `NATS_SERVERS` - NATS server URLs

## Architecture

This codebase uses a strict **3-layer architecture** with folder organization:

```
main.py (Orchestration)
    ↓
services/ (Layer 3: Business Logic)
    ↓
repositories/ (Layer 2: Data Access Patterns)
    ↓
db_clients/ (Layer 1: Pure CRUD)
```

### Layer 1: db_clients/ - Pure CRUD Operations
- `oracle_db_client.py` - Oracle connection and generic query execution
- `mariadb_db_client.py` - MariaDB connection and generic query execution
- `nats_client.py` - NATS JetStream connection, publish, batch operations

These clients contain **no business logic**, only connection management and basic CRUD operations.

### Layer 2: repositories/ - Data Access Patterns
- `oracle_repository.py` - Business-specific queries for Oracle (e.g., `get_txlog_events_since()`)
- `mariadb_repository.py` - ETL tracking queries (e.g., `get_last_successful_time()`, `update_successful_run()`)

Repositories encapsulate SQL queries and data access patterns. They use db_clients for execution.

### Layer 3: services/ - Business Logic
- `polling_service.py` - Orchestrates the polling workflow: fetch → publish → track

Services coordinate between repositories and publishers to implement business processes.

### Publishers (Business Logic for External Integrations)
- `txlog_event_publisher.py` - Formats Oracle records into TxLog events and publishes to NATS

Publishers are business logic layer components that handle external integrations. They use NatsClient for low-level operations.

### Key Flow: Poll and Publish
The main workflow in `PollingService.poll_and_publish()`:
1. Get last successful time from MariaDB tracking (via `mariadb_repository`)
2. Fetch new events from Oracle since that time (via `oracle_repository`)
3. Format and publish events to NATS (via `txlog_event_publisher`)
4. Update MariaDB tracking on success (via `mariadb_repository`)

### Important Architectural Rules
- **Synchronous only** - No async/await anywhere in the codebase
- **Layer separation** - Each layer only calls the layer below it
- **No business logic in db_clients** - Keep them pure CRUD
- **Publishers use db_clients** - TxLogEventPublisher uses NatsClient for CRUD operations
- **main.py is pure orchestration** - No business logic, just wiring components together

## Data Models

### Oracle Source Table
- `spc.TXLOG_EVENTS` - Transaction log events with columns: ID, CASE_ID, EVENT_TYPE, EVENT_DATA, EVENT_TIMESTAMP, CREATED_AT

### MariaDB Tracking Table
- `ETL_PRMREC` - Program tracking with columns: PROGRAM_NAME, LAST_SUCCESSFUL_TIME, LAST_RUN_TIME, STATUS, RECORDS_PROCESSED, ERROR_MESSAGE, CREATED_AT, UPDATED_AT
- Model: `models/etl_pgmrec.py` (EtlProgramRecord dataclass)

### NATS Publishing
- Stream: Configured in `config.yaml` under `intime_txlog_events.stream_name`
- Subject: Configured in `config.yaml` under `intime_txlog_events.subject`
- Events include `trace_id` (UUID) and `data_type` fields added by TxLogEventPublisher
- Batch publishing with retry mechanism (configurable via `publisher.batch_size` and `publisher.max_retries`)

## Configuration Structure

Key config sections in `config/config.yaml`:
- `oracle_db`: Oracle connection parameters
- `mariadb`: MariaDB connection parameters
- `nats`: NATS servers and connection settings
- `intime_txlog_events`: TxLog-specific settings (stream, subject, trace_id, data_type)
- `publisher`: Program name, polling interval, batch size, max records per run, max retries
- `logging`: Log level and format

## Utilities

- `utils/utils.py`: Contains `parse_datetime()` and `format_datetime()` helpers used throughout the codebase for consistent datetime handling
