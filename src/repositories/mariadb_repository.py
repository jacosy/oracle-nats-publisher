"""
MariaDB Repository
Data access patterns for ETL tracking
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from db_clients.mariadb_db_client import MariaDbClient
from models.etl_pgmrec import EtlProgramRecord

logger = logging.getLogger(__name__)


class MariaDbRepository:
    """
    Repository for MariaDB ETL tracking
    Contains business-specific queries for ETL_PRMREC table
    """
    
    def __init__(self, db_client: MariaDbClient):
        """
        Initialize repository
        
        Args:
            db_client: Pure CRUD database client
        """
        self.db_client = db_client
    
    def get_program_record(self, program_name: str) -> Optional[EtlProgramRecord]:
        """
        Get ETL program record by name
        
        Args:
            program_name: Program identifier
            
        Returns:
            EtlProgramRecord or None if not found
        """
        query = """
            SELECT 
                PROGRAM_NAME,
                LAST_SUCCESSFUL_TIME,
                LAST_RUN_TIME,
                STATUS,
                RECORDS_PROCESSED,
                ERROR_MESSAGE,
                CREATED_AT,
                UPDATED_AT
            FROM ETL_PRMREC
            WHERE PROGRAM_NAME = %s
        """
        
        try:
            records = self.db_client.execute_query(query, (program_name,))
            if records:
                logger.debug(f"Found program record for {program_name}")
                return EtlProgramRecord.from_dict(records[0])
            else:
                logger.debug(f"No program record found for {program_name}")
                return None
        except Exception as e:
            logger.error(f"Failed to get program record: {e}")
            raise
    
    def get_last_successful_time(self, program_name: str) -> Optional[datetime]:
        """
        Get last successful execution time for a program
        
        Args:
            program_name: Program identifier
            
        Returns:
            Last successful time or None
        """
        record = self.get_program_record(program_name)
        
        if record and record.last_successful_time:
            return record.last_successful_time
        
        logger.info(f"No last successful time found for {program_name}")
        return None
    
    def create_program_record(self, program_name: str) -> int:
        """
        Create new ETL program record
        
        Args:
            program_name: Program identifier
            
        Returns:
            Number of rows inserted
        """
        query = """
            INSERT INTO ETL_PRMREC (
                PROGRAM_NAME,
                STATUS,
                CREATED_AT,
                UPDATED_AT
            ) VALUES (%s, %s, %s, %s)
        """
        
        now = datetime.now()
        params = (program_name, 'INITIALIZED', now, now)
        
        try:
            rows = self.db_client.execute_update(query, params)
            logger.info(f"Created program record for {program_name}")
            return rows
        except Exception as e:
            logger.error(f"Failed to create program record: {e}")
            raise
    
    def update_successful_run(self, program_name: str, success_time: datetime, 
                             records_processed: int = 0) -> int:
        """
        Update program record after successful run
        
        Args:
            program_name: Program identifier
            success_time: Time of successful completion
            records_processed: Number of records processed
            
        Returns:
            Number of rows updated
        """
        query = """
            UPDATE ETL_PRMREC
            SET LAST_SUCCESSFUL_TIME = %s,
                LAST_RUN_TIME = %s,
                STATUS = %s,
                RECORDS_PROCESSED = RECORDS_PROCESSED + %s,
                ERROR_MESSAGE = NULL,
                UPDATED_AT = %s
            WHERE PROGRAM_NAME = %s
        """
        
        now = datetime.now()
        params = (success_time, now, 'SUCCESS', records_processed, now, program_name)
        
        try:
            rows = self.db_client.execute_update(query, params)
            logger.info(f"Updated successful run for {program_name}")
            return rows
        except Exception as e:
            logger.error(f"Failed to update successful run: {e}")
            raise
    
    def update_failed_run(self, program_name: str, error_message: str) -> int:
        """
        Update program record after failed run
        
        Args:
            program_name: Program identifier
            error_message: Error description
            
        Returns:
            Number of rows updated
        """
        query = """
            UPDATE ETL_PRMREC
            SET LAST_RUN_TIME = %s,
                STATUS = %s,
                ERROR_MESSAGE = %s,
                UPDATED_AT = %s
            WHERE PROGRAM_NAME = %s
        """
        
        now = datetime.now()
        params = (now, 'FAILED', error_message[:500], now, program_name)  # Limit error message
        
        try:
            rows = self.db_client.execute_update(query, params)
            logger.info(f"Updated failed run for {program_name}")
            return rows
        except Exception as e:
            logger.error(f"Failed to update failed run: {e}")
            raise
    
    def ensure_program_exists(self, program_name: str) -> None:
        """
        Ensure program record exists, create if not
        
        Args:
            program_name: Program identifier
        """
        record = self.get_program_record(program_name)
        if not record:
            self.create_program_record(program_name)
            logger.info(f"Created new program record: {program_name}")
        else:
            logger.debug(f"Program record exists: {program_name}")
