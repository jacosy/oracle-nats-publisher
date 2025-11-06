"""
MariaDB Database Client
Pure CRUD operations - no business logic
"""

import logging
import mysql.connector
from mysql.connector import pooling
from datetime import datetime
from typing import List, Dict, Any, Optional
from utils.retry_utils import retry_sync, create_retry_config_from_dict, RetryConfig

logger = logging.getLogger(__name__)


class MariaDbClient:
    """Pure CRUD operations for MariaDB with retry support"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connection_pool = None

        # Initialize retry configuration
        retry_config = config.get('retry', {})
        self.retry_config = create_retry_config_from_dict(retry_config)
        logger.info(f"MariaDB retry config: max_retries={self.retry_config.max_retries}, "
                   f"initial_backoff={self.retry_config.initial_backoff}s, "
                   f"max_backoff={self.retry_config.max_backoff}s")

        self._init_connection_pool()
    
    def _init_connection_pool(self):
        """Initialize connection pool"""
        try:
            self.connection_pool = pooling.MySQLConnectionPool(
                pool_name="mariadb_pool",
                pool_size=self.config.get('pool_size', 5),
                host=self.config['host'],
                port=self.config.get('port', 3306),
                database=self.config['database'],
                user=self.config['username'],
                password=self.config['password']
            )
            logger.info(f"MariaDB connection pool created")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}", exc_info=True)
            raise
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """
        Execute SELECT query with automatic retry on transient failures

        Args:
            query: SQL SELECT statement
            params: Query parameters as tuple

        Returns:
            List of records as dictionaries

        Raises:
            Exception: If query execution fails after all retries
        """
        # Create retry decorator dynamically based on instance config
        retry_decorator = retry_sync(self.retry_config)
        return retry_decorator(self._execute_query_internal)(query, params)

    def _execute_query_internal(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Internal implementation of execute_query (wrapped by retry logic)"""
        connection = None
        cursor = None
        try:
            connection = self.connection_pool.get_connection()
            cursor = connection.cursor(dictionary=True)

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            records = cursor.fetchall()

            # Convert datetime to ISO string
            for record in records:
                for key, value in record.items():
                    if isinstance(value, datetime):
                        record[key] = value.isoformat()

            return records

        except Exception as e:
            logger.error(f"Query error: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def execute_update(self, query: str, params: tuple = None) -> int:
        """
        Execute INSERT/UPDATE/DELETE query with automatic retry on transient failures

        Args:
            query: SQL DML statement
            params: Query parameters as tuple

        Returns:
            Number of rows affected

        Raises:
            Exception: If update execution fails after all retries
        """
        # Create retry decorator dynamically based on instance config
        retry_decorator = retry_sync(self.retry_config)
        return retry_decorator(self._execute_update_internal)(query, params)

    def _execute_update_internal(self, query: str, params: tuple = None) -> int:
        """Internal implementation of execute_update (wrapped by retry logic)"""
        connection = None
        cursor = None
        try:
            connection = self.connection_pool.get_connection()
            cursor = connection.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            connection.commit()
            return cursor.rowcount

        except Exception as e:
            if connection:
                connection.rollback()
            logger.error(f"Update error: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def close(self):
        """
        Close connection pool and release resources

        Handles race conditions:
        - Pool creation in-progress
        - No pool established
        - Pool already released
        """
        try:
            if self.connection_pool is None:
                logger.info("MariaDB connection pool not established, nothing to close")
                return

            # Note: MySQL connection pool doesn't have an explicit close method
            # Connections will be closed when they're returned to the pool
            # Set pool to None to allow garbage collection
            logger.info("Releasing MariaDB connection pool...")
            self.connection_pool = None
            logger.info("MariaDB connection pool released successfully")

        except Exception as e:
            logger.error(f"Error releasing MariaDB connection pool: {e}", exc_info=True)
            self.connection_pool = None
