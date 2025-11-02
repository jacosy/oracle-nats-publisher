"""
Oracle Database Client
Pure CRUD operations - no business logic
"""

import logging
import oracledb
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class OracleDbClient:
    """Pure CRUD operations for Oracle database"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connection_pool = None
        self._init_connection_pool()
    
    def _init_connection_pool(self):
        """Initialize connection pool"""
        try:
            self.connection_pool = oracledb.create_pool(
                user=self.config['user'],
                password=self.config['password'],
                dsn=self.config['dsn'],
                min=self.config.get('pool_min', 1),
                max=self.config.get('pool_max', 5),
                increment=self.config.get('pool_increment', 1)
            )
            logger.info(f"Oracle connection pool created")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise
    
    def execute_query(self, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Execute SELECT query
        
        Args:
            query: SQL SELECT statement
            params: Query parameters
            
        Returns:
            List of records as dictionaries
        """
        connection = None
        cursor = None
        try:
            connection = self.connection_pool.acquire()
            cursor = connection.cursor()
            
            if params:
                cursor.execute(query, **params)
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
            logger.error(f"Query error: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def close(self):
        """Close connection pool"""
        if self.connection_pool:
            self.connection_pool.close()
            logger.info("Oracle connection pool closed")
