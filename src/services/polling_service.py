"""
Polling Service
Business logic layer for polling and publishing operations
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from repositories.oracle_repository import OracleRepository
from repositories.mariadb_repository import MariaDbRepository
from publishers.txlog_event_publisher import TxLogEventPublisher
from models.etl_pgmrec import EtlProgramRecord

logger = logging.getLogger(__name__)


class PollingService:
    """
    Business logic for polling data and publishing to NATS
    Orchestrates data fetching, publishing, and tracking
    """
    
    def __init__(
        self,
        oracle_repo: OracleRepository,
        mariadb_repo: MariaDbRepository,
        txlog_publisher: TxLogEventPublisher
    ) -> None:
        """
        Initialize polling service

        Args:
            oracle_repo: Oracle data repository
            mariadb_repo: MariaDB tracking repository
            txlog_publisher: TxLog event publisher for message publishing
        """
        self.oracle_repo = oracle_repo
        self.mariadb_repo = mariadb_repo
        self.txlog_publisher = txlog_publisher
    
    def initialize_program(self, program_name: str) -> None:
        """
        Initialize program - ensure tracking record exists
        
        Args:
            program_name: Program identifier
        """
        logger.info(f"Initializing program: {program_name}")
        self.mariadb_repo.ensure_program_exists(program_name)
    
    async def poll_and_publish(
        self,
        program_name: str,
        max_records: int = 10000,
        batch_size: int = 100,
        max_retries: int = 3
    ) -> int:
        """
        Poll new events and publish to NATS with async batch publishing

        Complete workflow:
        1. Get last successful time from tracking
        2. Fetch new events from Oracle
        3. Publish events to NATS in async batches with retry
        4. Update tracking on success

        Args:
            program_name: Program identifier
            max_records: Maximum records to fetch
            batch_size: Batch size for publishing
            max_retries: Maximum retry attempts for failed messages

        Returns:
            Number of successfully published records
        """
        try:
            # Step 1: Get last successful time from tracking
            last_time = self.mariadb_repo.get_last_successful_time(program_name)

            if last_time:
                logger.info(f"Polling events since {last_time}")
            else:
                logger.info(f"No previous run found, polling all events (up to {max_records})")

            # Step 2: Fetch events from Oracle
            events = self.oracle_repo.get_txlog_events_since(last_time, max_records)

            if not events:
                logger.info("No new events to publish")
                return 0

            logger.info(f"Fetched {len(events)} new events")

            # Step 3: Publish to NATS with async batch retry
            published_count = await self.txlog_publisher.publish_batch(events, batch_size, max_retries)

            if published_count > 0:
                # Step 4: Update tracking on success
                success_time = datetime.now()
                self.mariadb_repo.update_successful_run(
                    program_name,
                    success_time,
                    published_count
                )
                logger.info(f"Successfully polled and published {published_count} records")
            else:
                logger.warning("No records were successfully published")

            return published_count

        except Exception as e:
            error_msg = f"Error during poll and publish: {e}"
            logger.error(error_msg, exc_info=True)

            # Mark failed run
            try:
                self.mariadb_repo.update_failed_run(program_name, str(e))
            except Exception as track_error:
                logger.error(f"Failed to mark run as failed: {track_error}")

            raise
    
    def get_program_status(self, program_name: str) -> Optional[EtlProgramRecord]:
        """
        Get current status of program
        
        Args:
            program_name: Program identifier
            
        Returns:
            EtlProgramRecord or None if not found
        """
        return self.mariadb_repo.get_program_record(program_name)
    
    def fetch_events_by_criteria(
        self,
        event_type: Optional[str] = None,
        case_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Fetch events by specific criteria (for ad-hoc queries)
        
        Args:
            event_type: Filter by event type
            case_id: Filter by case ID
            since: Filter by time
            limit: Maximum records
            
        Returns:
            List of matching events
        """
        if case_id:
            return self.oracle_repo.get_events_by_case_id(case_id)
        elif event_type:
            return self.oracle_repo.get_events_by_type(event_type, since, limit)
        else:
            return self.oracle_repo.get_txlog_events_since(since, limit)
