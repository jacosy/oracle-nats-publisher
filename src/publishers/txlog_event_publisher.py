"""
TxLog Event Publisher
Business logic layer for publishing TxLog events to NATS
"""

import logging
import uuid
from typing import List, Dict, Any
from datetime import datetime
from db_clients.nats_client import NatsClient
from utils import format_datetime

logger = logging.getLogger(__name__)


class TxLogEventPublisher:
    """
    TxLog Event Publisher
    Business logic for publishing TxLog events
    Uses NatsClient for low-level NATS operations
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize TxLog event publisher
        
        Args:
            config: Configuration containing:
                - nats: NATS connection config (servers, auth, etc.)
                - intime_txlog_events: TxLog-specific settings (stream, subject, etc.)
        """
        self.config = config
        
        # Extract TxLog event config
        self.txlog_config = config.get('intime_txlog_events', {})
        self.stream_name = self.txlog_config.get('stream_name', 'TXLOG_STREAM')
        self.subject = self.txlog_config.get('subject', 'txlog.events')
        self.add_trace_id = self.txlog_config.get('add_trace_id', True)
        self.data_type = self.txlog_config.get('data_type', 'TXLOG')
        
        # Create underlying NATS client with connection config
        nats_config = config.get('nats', {})
        self.nats_client = NatsClient(nats_config)
        
        logger.info(f"TxLog Event Publisher initialized: stream={self.stream_name}, subject={self.subject}")
    
    def connect(self) -> None:
        """
        Connect to NATS server
        """
        self.nats_client.connect()
        
        # Ensure stream exists for TxLog events
        self.nats_client.ensure_stream(self.stream_name, [self.subject])
        
        logger.info("TxLog Event Publisher connected")
    
    def format_txlog_event(self, oracle_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format Oracle record into TxLog event structure
        
        Applies business rules:
        - Add trace_id if enabled
        - Add data_type
        - Format datetime fields to ISO format
        
        Args:
            oracle_record: Raw Oracle database record
            
        Returns:
            Formatted TxLog event
        """
        event = {}
        
        # Add trace_id if enabled
        if self.add_trace_id:
            event['trace_id'] = str(uuid.uuid4())
        
        # Add data_type
        event['data_type'] = self.data_type
        
        # Copy all fields from Oracle record
        for key, value in oracle_record.items():
            # Format datetime fields
            if isinstance(value, datetime):
                value = format_datetime(value)
            
            event[key] = value
        
        return event
    
    def publish_event(self, oracle_record: Dict[str, Any]) -> bool:
        """
        Format and publish single TxLog event
        
        Args:
            oracle_record: Oracle database record
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Format event
            event = self.format_txlog_event(oracle_record)
            
            # Publish via NATS client
            return self.nats_client.publish(self.subject, event)
            
        except Exception as e:
            logger.error(f"Failed to publish TxLog event: {e}", exc_info=True)
            return False
    
    def publish_batch(self, oracle_records: List[Dict[str, Any]], 
                     batch_size: int = 100, max_retries: int = 3) -> int:
        """
        Format and publish batch of TxLog events with batching and retry support
        
        Formats all Oracle records and publishes them in batches with automatic retry.
        
        Args:
            oracle_records: List of Oracle database records
            batch_size: Number of events to publish per batch (default: 100)
            max_retries: Maximum retry attempts for failed messages (default: 3)
            
        Returns:
            Number of successfully published events
        """
        if not oracle_records:
            logger.warning("No records to publish")
            return 0
        
        try:
            total_records = len(oracle_records)
            logger.info(f"Starting to publish {total_records} TxLog events (batch_size={batch_size}, max_retries={max_retries})")
            
            # Format all events first
            formatted_events = []
            format_failed = 0
            
            for i, record in enumerate(oracle_records, 1):
                try:
                    event = self.format_txlog_event(record)
                    formatted_events.append(event)
                except Exception as e:
                    format_failed += 1
                    logger.error(f"Failed to format record {i}: {e}")
            
            if format_failed > 0:
                logger.warning(f"Failed to format {format_failed}/{total_records} records")
            
            if not formatted_events:
                logger.error("No events to publish after formatting")
                return 0
            
            # Publish via NATS client with batching and retry
            published_count = self.nats_client.publish_batch(
                self.subject,
                formatted_events,
                batch_size,
                max_retries
            )
            
            success_rate = (published_count / len(formatted_events)) * 100
            logger.info(f"TxLog Event Publisher: {published_count}/{len(formatted_events)} events published ({success_rate:.1f}% success rate)")
            
            return published_count
            
        except Exception as e:
            logger.error(f"Failed to publish TxLog batch: {e}", exc_info=True)
            return 0
    
    def close(self) -> None:
        """
        Close connection
        """
        self.nats_client.close()
        logger.info("TxLog Event Publisher closed")
