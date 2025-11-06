"""
Oracle Database Client
Pure CRUD operations - no business logic
"""

import logging
import oracledb
from datetime import datetime
from typing import List, Dict, Any, Optional
from utils.retry_utils import retry_sync, create_retry_config_from_dict, RetryConfig

logger = logging.getLogger(__name__)


class OracleDbClient:
    """Pure CRUD operations for Oracle database with retry support"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connection_pool = None

        # Initialize retry configuration
        retry_config = config.get('retry', {})
        self.retry_config = create_retry_config_from_dict(retry_config)
        logger.info(f"Oracle retry config: max_retries={self.retry_config.max_retries}, "
                   f"initial_backoff={self.retry_config.initial_backoff}s, "
                   f"max_backoff={self.retry_config.max_backoff}s")

        self._init_connection_pool()
    
    def _init_connection_pool(self):
        """Initialize connection pool"""
        try:
            self.connection_pool = oracledb.create_pool(
                user=self.config['username'],
                password=self.config['password'],
                dsn=self.config['dsn'],
                min=self.config.get('pool_min', 1),
                max=self.config.get('pool_max', 5),
                increment=self.config.get('pool_increment', 1)
            )
            logger.info(f"Oracle connection pool created")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}", exc_info=True)
            raise
    
    def execute_query(self, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Execute SELECT query with automatic retry on transient failures

        Args:
            query: SQL SELECT statement with named parameters (e.g., :param_name)
            params: Query parameters as dictionary with named parameters

        Returns:
            List of records as dictionaries

        Raises:
            Exception: If query execution fails after all retries
        """
        # Create retry decorator dynamically based on instance config
        retry_decorator = retry_sync(self.retry_config)
        return retry_decorator(self._execute_query_internal)(query, params)

    def _execute_query_internal(self, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Internal implementation of execute_query (wrapped by retry logic)"""
        connection = None
        cursor = None
        try:
            connection = self.connection_pool.acquire()
            cursor = connection.cursor()

            # Execute with named parameters (don't unpack with **)
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            columns = [col[0] for col in cursor.description]
            records = []

            for row in cursor.fetchall():
                record = dict(zip(columns, row))
                # Convert datetime to ISO string
                for key, value in record.items():
                    if isinstance(value, datetime):
                        record[key] = value.isoformat()
                records.append(record)

            return records

        except Exception as e:
            logger.error(f"Query execution failed: {e}", exc_info=True)
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def close(self):
        """
        Close connection pool gracefully

        Handles race conditions:
        - Pool creation in-progress
        - No pool established
        - Pool already closed
        """
        try:
            if self.connection_pool is None:
                logger.info("Oracle connection pool not established, nothing to close")
                return

            logger.info("Closing Oracle connection pool...")
            self.connection_pool.close()
            logger.info("Oracle connection pool closed successfully")

        except Exception as e:
            logger.error(f"Error closing Oracle connection pool: {e}", exc_info=True)
        finally:
            # Ensure state is reset
            self.connection_pool = None
