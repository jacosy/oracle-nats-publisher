"""
ETL Program Record Data Type
Represents a record from the ETL_PRMREC table
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from utils.utils import parse_datetime, format_datetime


@dataclass
class EtlProgramRecord:
    """
    Data type for ETL_PRMREC table records
    
    Represents the tracking information for ETL programs
    """
    
    program_name: str
    last_successful_time: Optional[datetime] = None
    last_run_time: Optional[datetime] = None
    status: Optional[str] = None
    records_processed: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> 'EtlProgramRecord':
        """
        Create EtlProgramRecord from dictionary
        
        Args:
            data: Dictionary with database column names as keys
            
        Returns:
            EtlProgramRecord instance
        """
        # Handle both uppercase and lowercase keys
        program_name = data.get('PROGRAM_NAME') or data.get('program_name')
        
        # Parse datetime fields using utility function
        last_successful_time = parse_datetime(
            data.get('LAST_SUCCESSFUL_TIME') or data.get('last_successful_time')
        )
        last_run_time = parse_datetime(
            data.get('LAST_RUN_TIME') or data.get('last_run_time')
        )
        created_at = parse_datetime(
            data.get('CREATED_AT') or data.get('created_at')
        )
        updated_at = parse_datetime(
            data.get('UPDATED_AT') or data.get('updated_at')
        )
        
        # Get other fields
        status = data.get('STATUS') or data.get('status')
        records_processed = data.get('RECORDS_PROCESSED') or data.get('records_processed') or 0
        error_message = data.get('ERROR_MESSAGE') or data.get('error_message')
        
        return cls(
            program_name=program_name,
            last_successful_time=last_successful_time,
            last_run_time=last_run_time,
            status=status,
            records_processed=records_processed,
            error_message=error_message,
            created_at=created_at,
            updated_at=updated_at
        )
    
    def to_dict(self) -> dict:
        """
        Convert EtlProgramRecord to dictionary
        
        Returns:
            Dictionary with database column names as keys
        """
        return {
            'PROGRAM_NAME': self.program_name,
            'LAST_SUCCESSFUL_TIME': format_datetime(self.last_successful_time),
            'LAST_RUN_TIME': format_datetime(self.last_run_time),
            'STATUS': self.status,
            'RECORDS_PROCESSED': self.records_processed,
            'ERROR_MESSAGE': self.error_message,
            'CREATED_AT': format_datetime(self.created_at),
            'UPDATED_AT': format_datetime(self.updated_at)
        }
    
    def is_successful(self) -> bool:
        """
        Check if the last run was successful
        
        Returns:
            True if status is SUCCESS, False otherwise
        """
        return self.status == 'SUCCESS'
    
    def is_failed(self) -> bool:
        """
        Check if the last run failed
        
        Returns:
            True if status is FAILED, False otherwise
        """
        return self.status == 'FAILED'
    
    def has_run_before(self) -> bool:
        """
        Check if the program has ever run successfully
        
        Returns:
            True if last_successful_time is set, False otherwise
        """
        return self.last_successful_time is not None
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return (
            f"EtlProgramRecord("
            f"program_name='{self.program_name}', "
            f"status='{self.status}', "
            f"last_successful_time={self.last_successful_time}, "
            f"records_processed={self.records_processed}"
            f")"
        )
