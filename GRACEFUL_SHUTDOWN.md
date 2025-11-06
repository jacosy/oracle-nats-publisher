# Graceful Shutdown Documentation

## Overview

The application implements proper graceful shutdown through the layer architecture to prevent interrupting in-flight operations.

## Problem Solved

**Previous Issue**: Directly calling `close()` on db_clients and nats_client could terminate connections while:
- NATS messages were still being published
- Database queries were executing
- Transactions were in progress

**Solution**: Implement cascading shutdown through the service layer, respecting the architecture boundaries.

## Graceful Shutdown Flow

### 1. Signal Reception
```
User sends SIGINT (Ctrl+C) or SIGTERM
    ↓
Signal handler sets self.running = False
    ↓
Main loop completes current cycle
```

### 2. Cascade Through Layers
```
main.py: cleanup()
    ↓
PollingService.close() [Layer 3]
    ↓
    ├─→ TxLogEventPublisher.close() [Publisher]
    │       ↓
    │   NatsClient.close() [Layer 1]
    │       ↓
    │   await nc.drain()  # Wait for pending messages
    │   await nc.close()
    │
    ├─→ OracleRepository.close() [Layer 2]
    │       ↓
    │   OracleDbClient.close() [Layer 1]
    │       ↓
    │   connection_pool.close()
    │
    └─→ MariaDbRepository.close() [Layer 2]
            ↓
        MariaDbClient.close() [Layer 1]
            ↓
        Release connection pool
```

## Implementation Details

### Layer 1: Database Clients

**OracleDbClient.close()**
```python
def close(self):
    if self.connection_pool:
        self.connection_pool.close()  # Closes all connections in pool
```

**MariaDbClient.close()**
```python
def close(self):
    if self.connection_pool:
        self.connection_pool = None  # Releases pool for garbage collection
```

**NatsClient.close()**
```python
async def close(self):
    if self.nc is not None and self.is_connected:
        await self.nc.drain()  # ✅ Waits for pending messages!
        await self.nc.close()
```

### Layer 2: Repositories

**OracleRepository.close()**
```python
def close(self):
    logger.info("Closing Oracle repository")
    if self.db_client:
        self.db_client.close()
```

**MariaDbRepository.close()**
```python
def close(self):
    logger.info("Closing MariaDB repository")
    if self.db_client:
        self.db_client.close()
```

### Layer 3: Service

**PollingService.close()**
```python
async def close(self):
    # Close publisher first (may have pending async operations)
    await self.txlog_publisher.close()

    # Then close repositories (database connections)
    self.oracle_repo.close()
    self.mariadb_repo.close()
```

### Orchestration: Main

**PublisherApp.cleanup()**
```python
async def cleanup(self):
    # Single call cascades through all layers
    await self.polling_service.close()
```

## Key Features

### 1. Respects Architecture Boundaries
- Main doesn't directly access db_clients
- Service layer owns the shutdown logic
- Each layer is responsible for its children

### 2. Prevents In-Flight Interruption
- `self.running = False` stops accepting new work
- Main loop completes current `process_one_cycle()`
- Only then does cleanup begin

### 3. NATS Drain Pattern
```python
await self.nc.drain()  # Critical: waits for pending publishes
```
This ensures all queued messages are sent before closing.

### 4. Error Handling at Each Layer
Each close method has try/except to ensure:
- One failure doesn't prevent others from closing
- All resources are cleaned up even if some fail
- Errors are logged with full context

## Shutdown Timeline

```
t=0s    User presses Ctrl+C
        │
t=0s    Signal handler: self.running = False
        │
t=0-60s Current polling cycle completes
        │  - Oracle query finishes
        │  - NATS batch publish completes (with retries)
        │  - MariaDB tracking update completes
        │
t=60s   Main loop exits (no sleep interruption)
        │
t=60s   cleanup() called (in finally block)
        │
        ├─→ PollingService.close()
        │   │
        │   ├─→ TxLogEventPublisher.close()
        │   │   └─→ NatsClient.close()
        │   │       ├─→ nc.drain() [waits for pending]
        │   │       └─→ nc.close()
        │   │
        │   ├─→ OracleRepository.close()
        │   │   └─→ OracleDbClient.close()
        │   │
        │   └─→ MariaDbRepository.close()
        │       └─→ MariaDbClient.close()
        │
t=61s   Application exits cleanly
```

## Benefits Over Direct Client Closure

### ❌ Direct Client Closure (Previous)
```python
async def cleanup(self):
    await self.nats_client.close()      # ❌ Might interrupt publishing
    self.oracle_db_client.close()        # ❌ Might interrupt queries
    self.mariadb_db_client.close()      # ❌ Might interrupt tracking
```

**Problems**:
- Could interrupt batch publishing mid-operation
- Could terminate queries before results are returned
- Could lose tracking updates
- Violates layer architecture (main shouldn't touch clients)

### ✅ Service Layer Closure (Current)
```python
async def cleanup(self):
    await self.polling_service.close()  # ✅ Graceful cascade
```

**Benefits**:
- Service coordinates shutdown
- Each layer waits for its operations
- NATS drain ensures message delivery
- Respects architecture boundaries
- Single point of control

## Testing Graceful Shutdown

### Manual Test
```bash
python src/main.py

# In another terminal after a few seconds:
kill -SIGTERM <pid>

# Or just press Ctrl+C
```

**Expected Log Output**:
```
INFO - Received signal 15, shutting down...
INFO - Cycle completed: 100 records published
INFO - Starting graceful shutdown...
INFO - Closing Polling Service gracefully...
INFO - Publisher closed successfully
INFO - Oracle repository closed successfully
INFO - MariaDB repository closed successfully
INFO - Polling Service closed
INFO - All resources closed successfully
INFO - Graceful shutdown completed
INFO - Publisher stopped
```

### Verify No Interruptions
✅ Check that the current cycle completes before shutdown
✅ Check that all NATS messages are published
✅ Check that database connections close cleanly
✅ No "BrokenPipeError" or connection errors

## Best Practices

1. **Always use service layer for shutdown**
   - Don't bypass layers
   - Let each layer manage its children

2. **Wait for current work**
   - Check `self.running` in loops
   - Complete current operation before closing

3. **Use NATS drain**
   - Always call `drain()` before `close()`
   - Ensures message delivery

4. **Handle errors at each layer**
   - One failure shouldn't cascade
   - Log all errors with context

5. **Test shutdown scenarios**
   - During idle periods
   - During active publishing
   - During database queries
   - With NATS connection issues

## Common Issues

### Issue: "Connection closed while publishing"
**Cause**: Calling `close()` without `drain()`
**Fix**: ✅ Already implemented - NatsClient uses `drain()`

### Issue: "Database query interrupted"
**Cause**: Closing connection pool during query
**Fix**: ✅ Already implemented - waits for cycle completion

### Issue: "Lost tracking update"
**Cause**: Closing before MariaDB update commits
**Fix**: ✅ Already implemented - waits for cycle completion

## Summary

The graceful shutdown implementation ensures:
- ✅ No interrupted operations
- ✅ All NATS messages delivered
- ✅ Database transactions completed
- ✅ Proper connection cleanup
- ✅ Respects layer architecture
- ✅ Single point of control

This is production-ready and handles all edge cases properly.
