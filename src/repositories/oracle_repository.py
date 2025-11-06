"""
Oracle Repository
Data access patterns for Oracle - contains business queries
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from db_clients.oracle_db_client import OracleDbClient

logger = logging.getLogger(__name__)


class OracleRepository:
    """
    Repository for Oracle data access
    Contains business-specific queries and data access patterns
    """

    def __init__(self, db_client: OracleDbClient):
        """
        Initialize repository

        Args:
            db_client: Pure CRUD database client
        """
        self.db_client = db_client

    def close(self) -> None:
        """
        Close repository and underlying database connection
        Ensures graceful shutdown of Oracle connections
        """
        logger.info("Closing Oracle repository")
        if self.db_client:
            self.db_client.close()
    
    def get_txlog_events_since(self, since: Optional[datetime], limit: int = 10000) -> List[Dict[str, Any]]:
        """
        Get transaction log events since a specific time

        Args:
            since: Get records created after this time (None = from beginning)
            limit: Maximum number of records to fetch

        Returns:
            List of TXLOG_EVENTS records
        """
        # Business logic: Default to epoch if no time specified
        # Note: Using naive datetime - Oracle session timezone will be used
        # For timezone-aware queries, ensure Oracle session is configured correctly
        if since is None:
            since = datetime(1970, 1, 1)
        elif since.tzinfo is not None:
            # Convert timezone-aware datetime to naive (Oracle will use session timezone)
            logger.debug(f"Converting timezone-aware datetime to naive: {since}")
            since = since.replace(tzinfo=None)

        # Business query for TXLOG_EVENTS
        query = """
            SELECT
                ID,
                CASE_ID,
                EVENT_TYPE,
                EVENT_DATA,
                EVENT_TIMESTAMP,
                CREATED_AT
            FROM spc.TXLOG_EVENTS
            WHERE CREATED_AT > :since_time
            ORDER BY CREATED_AT ASC
            FETCH FIRST :max_records ROWS ONLY
        """

        params = {
            'since_time': since,
            'max_records': limit
        }

        try:
            records = self.db_client.execute_query(query, params)
            logger.info(f"Fetched {len(records)} TXLOG_EVENTS records from Oracle (since: {since})")
            return records
        except Exception as e:
            logger.error(f"Failed to fetch TXLOG_EVENTS: {e}", exc_info=True)
            raise
    
    def get_events_by_case_id(self, case_id: str) -> List[Dict[str, Any]]:
        """
        Get all events for a specific case
        
        Args:
            case_id: Case identifier
            
        Returns:
            List of events for the case
        """
        query = """
            SELECT 
                ID,
                CASE_ID,
                EVENT_TYPE,
                EVENT_DATA,
                EVENT_TIMESTAMP,
                CREATED_AT
            FROM spc.TXLOG_EVENTS
            WHERE CASE_ID = :case_id
            ORDER BY CREATED_AT ASC
        """
        
        params = {'case_id': case_id}
        
        try:
            records = self.db_client.execute_query(query, params)
            logger.debug(f"Fetched {len(records)} events for case {case_id}")
            return records
        except Exception as e:
            logger.error(f"Failed to fetch events for case {case_id}: {e}")
            raise
    
    def get_events_by_type(self, event_type: str, since: Optional[datetime] = None, 
                          limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get events of a specific type
        
        Args:
            event_type: Type of event to fetch
            since: Get records after this time (optional)
            limit: Maximum records
            
        Returns:
            List of events
        """
        if since:
            query = """
                SELECT 
                    ID,
                    CASE_ID,
                    EVENT_TYPE,
                    EVENT_DATA,
                    EVENT_TIMESTAMP,
                    CREATED_AT
                FROM spc.TXLOG_EVENTS
                WHERE EVENT_TYPE = :event_type
                  AND CREATED_AT > :since_time
                ORDER BY CREATED_AT ASC
                FETCH FIRST :max_records ROWS ONLY
            """
            params = {
                'event_type': event_type,
                'since_time': since,
                'max_records': limit
            }
        else:
            query = """
                SELECT 
                    ID,
                    CASE_ID,
                    EVENT_TYPE,
                    EVENT_DATA,
                    EVENT_TIMESTAMP,
                    CREATED_AT
                FROM spc.TXLOG_EVENTS
                WHERE EVENT_TYPE = :event_type
                ORDER BY CREATED_AT DESC
                FETCH FIRST :max_records ROWS ONLY
            """
            params = {
                'event_type': event_type,
                'max_records': limit
            }
        
        try:
            records = self.db_client.execute_query(query, params)
            logger.debug(f"Fetched {len(records)} events of type {event_type}")
            return records
        except Exception as e:
            logger.error(f"Failed to fetch events of type {event_type}: {e}")
            raise
