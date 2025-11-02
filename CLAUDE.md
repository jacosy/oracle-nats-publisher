# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Oracle NATS Publisher V7 - A Python application that polls Oracle database for transaction log events and publishes them to NATS JetStream using **async/await** for high-throughput batch publishing, with ETL tracking in MariaDB.

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
- `oracle_db_client.py` - Oracle connection and generic query execution (synchronous)
- `mariadb_db_client.py` - MariaDB connection and generic query execution (synchronous)
- `nats_client.py` - NATS JetStream connection, publish, **async batch operations**

These clients contain **no business logic**, only connection management and basic CRUD operations. The NATS client uses async/await for high-throughput batch publishing.

### Layer 2: repositories/ - Data Access Patterns
- `oracle_repository.py` - Business-specific queries for Oracle (synchronous, e.g., `get_txlog_events_since()`)
- `mariadb_repository.py` - ETL tracking queries (synchronous, e.g., `get_last_successful_time()`, `update_successful_run()`)

Repositories encapsulate SQL queries and data access patterns. They use db_clients for execution. Database queries remain synchronous.

### Layer 3: services/ - Business Logic
- `polling_service.py` - Orchestrates the polling workflow: fetch → publish → track (**async**)

Services coordinate between repositories and publishers. The `poll_and_publish()` method is async to support high-throughput publishing.

### Publishers (Business Logic for External Integrations)
- `txlog_event_publisher.py` - Formats Oracle records into TxLog events and publishes to NATS (**async**)

Publishers are business logic layer components that handle external integrations. They use NatsClient for async batch operations.

### Key Flow: Poll and Publish
The main workflow in `PollingService.poll_and_publish()` (async):
1. Get last successful time from MariaDB tracking (synchronous, via `mariadb_repository`)
2. Fetch new events from Oracle since that time (synchronous, via `oracle_repository`)
3. Format and **async batch publish** events to NATS (via `txlog_event_publisher`)
4. Update MariaDB tracking on success (synchronous, via `mariadb_repository`)

The async nature is **only for NATS publishing** to achieve high throughput. Database operations remain synchronous.

### Important Architectural Rules
- **Hybrid sync/async** - Database operations are synchronous, NATS publishing is async for performance
- **Layer separation** - Each layer only calls the layer below it
- **No business logic in db_clients** - Keep them pure CRUD
- **Publishers use db_clients** - TxLogEventPublisher uses NatsClient for async batch operations
- **main.py is pure orchestration** - No business logic, just wiring components and running the async event loop
- **Async propagation** - Methods that call async operations must be async (poll_and_publish, process_one_cycle, run)

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
- **TRUE Async Batch Publishing**: `NatsClient.publish_batch()` handles:
  - Pre-serialization of all messages to catch format errors early
  - **Concurrent async publishing** using `asyncio.gather()` for maximum throughput
  - Messages in each batch are published **simultaneously** (not one-by-one)
  - Processing messages in configurable batches (via `publisher.batch_size`)
  - Automatic retry with exponential backoff (via `publisher.max_retries`)
  - Individual message retry (not transactional - messages succeed/fail independently)
  - Detailed progress tracking and error reporting

**Performance**: The async batch implementation publishes multiple messages concurrently within each batch, providing significantly higher throughput compared to sequential publishing.

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
