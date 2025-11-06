# Retry Implementation Documentation

## Overview

Robust retry mechanisms with configurable exponential backoff have been added to all database clients (Oracle, MariaDB, and NATS) to handle transient failures gracefully.

## Architecture

### Core Components

1. **`utils/retry_utils.py`** - Centralized retry utilities
   - `RetryConfig` class: Encapsulates retry configuration
   - `retry_sync()` decorator: For synchronous operations
   - `retry_async()` decorator: For asynchronous operations
   - `create_retry_config_from_dict()`: Helper to parse YAML config

### RetryConfig Class

```python
class RetryConfig:
    def __init__(
        self,
        max_retries: int = 3,              # Maximum retry attempts
        initial_backoff: float = 1.0,      # Initial wait time (seconds)
        max_backoff: float = 30.0,         # Maximum wait time (seconds)
        backoff_multiplier: float = 2.0,   # Exponential multiplier
        retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None
    )
```

## Configuration

### YAML Configuration Structure

Each client supports retry configuration in `config.yaml`:

```yaml
oracle_db:
  retry:
    max_retries: 3              # 0 = no retries, 1+ = retry attempts
    initial_backoff: 1.0        # Initial wait before first retry
    max_backoff: 30.0           # Cap on exponential backoff
    backoff_multiplier: 2.0     # Exponential growth factor

mariadb:
  retry:
    max_retries: 3
    initial_backoff: 1.0
    max_backoff: 30.0
    backoff_multiplier: 2.0

nats:
  retry:
    max_retries: 3
    initial_backoff: 1.0
    max_backoff: 10.0           # Lower max for NATS (faster ops)
    backoff_multiplier: 2.0
```

## Exponential Backoff Behavior

The retry mechanism uses exponential backoff with capping:

```
Attempt 1: initial_backoff × (multiplier^0) = 1.0s
Attempt 2: initial_backoff × (multiplier^1) = 2.0s
Attempt 3: initial_backoff × (multiplier^2) = 4.0s
Attempt 4: initial_backoff × (multiplier^3) = 8.0s
Attempt 5: initial_backoff × (multiplier^4) = 16.0s
...capped at max_backoff
```

### Example Timeline (max_retries=3)

```
t=0.0s    → First attempt fails
t=1.0s    → Retry #1 (after 1.0s backoff) fails
t=3.0s    → Retry #2 (after 2.0s backoff) fails
t=7.0s    → Retry #3 (after 4.0s backoff) fails
t=7.0s    → Raise exception (all retries exhausted)
```

## Client-Specific Implementation

### 1. OracleDbClient

**Modified Methods:**
- `execute_query()` - Now retries on transient database failures

**Implementation Pattern:**
```python
def execute_query(self, query: str, params: Dict[str, Any] = None):
    """Public method with retry wrapper"""
    retry_decorator = retry_sync(self.retry_config)
    return retry_decorator(self._execute_query_internal)(query, params)

def _execute_query_internal(self, query: str, params: Dict[str, Any] = None):
    """Internal method with actual logic"""
    # ... database query execution
```

**Location:** `src/db_clients/oracle_db_client.py`

### 2. MariaDbClient

**Modified Methods:**
- `execute_query()` - SELECT queries with retry
- `execute_update()` - INSERT/UPDATE/DELETE with retry

**Implementation Pattern:**
```python
def execute_query(self, query: str, params: tuple = None):
    retry_decorator = retry_sync(self.retry_config)
    return retry_decorator(self._execute_query_internal)(query, params)

def execute_update(self, query: str, params: tuple = None):
    retry_decorator = retry_sync(self.retry_config)
    return retry_decorator(self._execute_update_internal)(query, params)
```

**Location:** `src/db_clients/mariadb_db_client.py`

### 3. NatsClient

**Modified Methods:**
- `publish()` - Single message publish with retry
- `publish_batch()` - Uses instance config for batch retry logic

**Implementation Pattern:**
```python
async def publish(self, subject: str, message: Dict[str, Any]):
    """Public method with retry wrapper"""
    try:
        retry_decorator = retry_async(self.retry_config)
        await retry_decorator(self._publish_internal)(subject, message)
        return True
    except Exception as e:
        logger.error(f"Failed after all retries: {e}")
        return False

async def _publish_internal(self, subject: str, message: Dict[str, Any]):
    """Internal async method with actual logic"""
    # ... NATS publish logic
```

**Batch Publishing:**
- Uses `self.retry_config.calculate_backoff()` for retry delays
- Defaults `max_retries` parameter to `self.retry_config.max_retries` if not specified

**Location:** `src/db_clients/nats_client.py`

## Logging

The retry mechanism provides detailed logging at each stage:

### Initialization
```
INFO - Oracle retry config: max_retries=3, initial_backoff=1.0s, max_backoff=30.0s
INFO - MariaDB retry config: max_retries=3, initial_backoff=1.0s, max_backoff=30.0s
INFO - NATS retry config: max_retries=3, initial_backoff=1.0s, max_backoff=10.0s
```

### Retry Attempts
```
WARNING - execute_query failed (attempt 1/4): ORA-12170: TNS:Connect timeout occurred. Retrying in 1.00s...
WARNING - execute_query failed (attempt 2/4): ORA-12170: TNS:Connect timeout occurred. Retrying in 2.00s...
WARNING - execute_query failed (attempt 3/4): ORA-12170: TNS:Connect timeout occurred. Retrying in 4.00s...
ERROR - execute_query failed after 4 attempts: ORA-12170: TNS:Connect timeout occurred
```

## Benefits

### 1. **Resilience to Transient Failures**
- Network hiccups
- Temporary database unavailability
- NATS server restarts
- Connection pool exhaustion

### 2. **Configurable Behavior**
- Adjust retry counts per environment (dev vs prod)
- Tune backoff timing for different network conditions
- Disable retries entirely (`max_retries: 0`)

### 3. **Consistent Pattern**
- Same retry logic across all clients
- Centralized configuration
- Uniform logging format

### 4. **Non-Breaking Changes**
- Existing code works without modification
- Retry happens transparently
- Configuration is optional (defaults apply)

### 5. **Production Ready**
- Exponential backoff prevents thundering herd
- Max backoff prevents excessive delays
- Detailed logging for troubleshooting

## Migration Guide

### For Existing Deployments

1. **Add retry config to `config.yaml`:**
   ```yaml
   oracle_db:
     retry:
       max_retries: 3
       initial_backoff: 1.0
       max_backoff: 30.0
       backoff_multiplier: 2.0
   ```

2. **Test in development first:**
   - Simulate transient failures
   - Verify retry logs appear
   - Confirm backoff timing

3. **Tune for production:**
   - Adjust `max_retries` based on failure patterns
   - Set `max_backoff` appropriate for your SLAs
   - Consider higher `initial_backoff` for slower networks

### Default Behavior (No Config)

If `retry` section is omitted, defaults apply:
- `max_retries: 3`
- `initial_backoff: 1.0`
- `max_backoff: 30.0` (Oracle/MariaDB) or `10.0` (NATS)
- `backoff_multiplier: 2.0`

## Testing Retry Logic

### Manual Testing

1. **Simulate database outage:**
   ```bash
   # Stop Oracle/MariaDB temporarily
   docker stop oracle-container

   # Watch logs for retry attempts
   tail -f logs/app.log

   # Restart database
   docker start oracle-container
   ```

2. **Simulate NATS outage:**
   ```bash
   # Stop NATS server
   docker stop nats-server

   # Application will retry with exponential backoff
   # Restart NATS
   docker start nats-server
   ```

### Unit Testing

Create tests in `tests/test_retry_utils.py`:
```python
def test_exponential_backoff():
    config = RetryConfig(max_retries=3, initial_backoff=1.0, backoff_multiplier=2.0)
    assert config.calculate_backoff(0) == 1.0
    assert config.calculate_backoff(1) == 2.0
    assert config.calculate_backoff(2) == 4.0
```

## Best Practices

1. **Set reasonable max_retries:**
   - Too low: Fails on transient issues
   - Too high: Delays error detection
   - Recommended: 3-5 for most cases

2. **Tune backoff for operation type:**
   - Fast operations (NATS): Lower max_backoff (10s)
   - Slow operations (DB queries): Higher max_backoff (30s)

3. **Monitor retry rates:**
   - High retry rates indicate infrastructure issues
   - Add metrics/alerts on retry frequency

4. **Consider idempotency:**
   - Ensure retried operations are safe to repeat
   - MariaDB UPDATE tracking is idempotent
   - NATS publishes are idempotent (JetStream deduplication)

## Troubleshooting

### Issue: Too many retries
**Symptom:** Operations take too long to fail
**Solution:** Reduce `max_retries` or `max_backoff`

### Issue: Not enough retries
**Symptom:** Failures on transient issues
**Solution:** Increase `max_retries` or `initial_backoff`

### Issue: Retry logs not appearing
**Symptom:** No retry attempt logs
**Solution:** Check log level is at least WARNING

### Issue: All retries fail immediately
**Symptom:** No backoff delays observed
**Solution:** Verify `initial_backoff` > 0 in config

## Performance Impact

- **Memory:** Negligible (config objects are lightweight)
- **CPU:** Minimal (sleep during backoff)
- **Latency:**
  - Success case: No overhead
  - Retry case: Adds backoff delays (expected behavior)
- **Throughput:** No impact on successful operations

## Future Enhancements

Potential improvements for future iterations:

1. **Jitter:** Add randomization to prevent thundering herd
2. **Circuit Breaker:** Stop retrying after repeated failures
3. **Selective Retry:** Only retry specific exception types
4. **Metrics:** Expose retry counts to Prometheus/metrics system
5. **Per-Operation Config:** Different retry settings per query type

## Summary

The retry implementation provides:
- ✅ **Robust error handling** with exponential backoff
- ✅ **Configurable behavior** via YAML
- ✅ **Consistent implementation** across all clients
- ✅ **Production-ready** with comprehensive logging
- ✅ **Zero breaking changes** to existing code
- ✅ **Well-documented** with examples and best practices

All database operations now automatically retry transient failures, improving application resilience without requiring code changes.
