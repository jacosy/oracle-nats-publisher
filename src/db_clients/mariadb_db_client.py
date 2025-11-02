"""
MariaDB Database Client
Pure CRUD operations - no business logic
"""

import logging
import mysql.connector
from mysql.connector import pooling
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class MariaDbClient:
    """Pure CRUD operations for MariaDB"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connection_pool = None
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
                user=self.config['user'],
                password=self.config['password']
            )
            logger.info(f"MariaDB connection pool created")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """
        Execute SELECT query
        
        Args:
            query: SQL SELECT statement
            params: Query parameters as tuple
            
        Returns:
            List of records as dictionaries
        """
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
        Execute INSERT/UPDATE/DELETE query
        
        Args:
            query: SQL DML statement
            params: Query parameters as tuple
            
        Returns:
            Number of rows affected
        """
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
        """Close connection pool"""
        if self.connection_pool:
            # Connection pool doesn't have close method, connections auto-close
            logger.info("MariaDB connections will auto-close")
