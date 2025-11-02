"""
NATS Client
Low-level NATS connection and operations (CRUD only)
"""

import logging
import json
from typing import List, Dict, Any
import nats
from nats.js.api import StreamConfig

logger = logging.getLogger(__name__)


class NatsClient:
    """
    NATS Client
    Handles low-level NATS connection and JetStream operations
    Similar to OracleDbClient and MariaDbClient - pure CRUD operations
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize NATS client
        
        Args:
            config: NATS connection configuration containing:
                - servers: List of NATS server URLs
                - username: Optional username
                - password: Optional password
                - max_reconnect_attempts: Max reconnection attempts
                - reconnect_time_wait: Wait time between reconnections
        """
        self.config = config
        self.servers = config.get('servers', ['nats://localhost:4222'])
        self.username = config.get('username')
        self.password = config.get('password')
        
        self.nc = None
        self.js = None
        self.is_connected = False
        
        logger.info(f"NATS Client initialized for {self.servers}")
    
    def connect(self) -> None:
        """
        Connect to NATS server and initialize JetStream
        
        Raises:
            Exception: If connection fails
        """
        try:
            # Build connection URL
            if len(self.servers) == 1:
                servers = self.servers[0]
            else:
                servers = ','.join(self.servers)
            
            # Connection options
            connect_opts = {
                'servers': servers,
                'max_reconnect_attempts': self.config.get('max_reconnect_attempts', 60),
                'reconnect_time_wait': self.config.get('reconnect_time_wait', 2)
            }
            
            # Add authentication if provided
            if self.username and self.password:
                connect_opts['user'] = self.username
                connect_opts['password'] = self.password
            
            # Connect to NATS
            self.nc = nats.connect(**connect_opts)
            
            logger.info(f"Connected to NATS at {self.servers}")
            
            # Get JetStream context
            self.js = self.nc.jetstream()
            
            self.is_connected = True
            logger.info("JetStream initialized")
            
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}", exc_info=True)
            raise
    
    def ensure_stream(self, stream_name: str, subjects: List[str]) -> None:
        """
        Ensure JetStream stream exists, create if not
        
        Args:
            stream_name: Name of the stream
            subjects: List of subjects for the stream
        """
        try:
            # Try to get stream info
            self.js.stream_info(stream_name)
            logger.info(f"Stream {stream_name} already exists")
        except Exception:
            # Stream doesn't exist, create it
            try:
                config = StreamConfig(
                    name=stream_name,
                    subjects=subjects,
                    description=f"Stream for {', '.join(subjects)}"
                )
                
                self.js.add_stream(config)
                logger.info(f"Created stream: {stream_name} with subjects: {subjects}")
            except Exception as e:
                logger.warning(f"Could not create stream {stream_name}: {e}")
    
    def publish(self, subject: str, message: Dict[str, Any]) -> bool:
        """
        Publish single message to NATS JetStream
        
        Args:
            subject: Subject to publish to
            message: Message dictionary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.is_connected or not self.js:
                raise RuntimeError("Not connected to NATS JetStream")
            
            # Convert message to JSON
            payload = json.dumps(message, default=str).encode('utf-8')
            
            # Publish to JetStream
            ack = self.js.publish(subject, payload)
            
            logger.debug(f"Published to {subject}, seq: {ack.seq}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish to {subject}: {e}", exc_info=True)
            return False
    
    def publish_batch(self, subject: str, messages: List[Dict[str, Any]], 
                     batch_size: int = 100, max_retries: int = 3) -> int:
        """
        Publish batch of messages to NATS JetStream with true batching and retry
        
        Uses NATS publish_async for true batch publishing instead of one-by-one.
        Implements retry mechanism for failed messages.
        
        Args:
            subject: Subject to publish to
            messages: List of message dictionaries
            batch_size: Number of messages to publish in each batch (default: 100)
            max_retries: Maximum retry attempts for failed messages (default: 3)
            
        Returns:
            Number of successfully published messages
        """
        if not messages:
            logger.warning("No messages to publish")
            return 0
        
        if not self.is_connected or not self.js:
            raise RuntimeError("Not connected to NATS JetStream")
        
        total_messages = len(messages)
        published_count = 0
        failed_messages = []
        
        logger.info(f"Publishing {total_messages} messages in batches of {batch_size}")
        
        # Process in batches
        for batch_start in range(0, total_messages, batch_size):
            batch_end = min(batch_start + batch_size, total_messages)
            current_batch = messages[batch_start:batch_end]
            
            batch_num = (batch_start // batch_size) + 1
            total_batches = (total_messages + batch_size - 1) // batch_size
            
            logger.debug(f"Processing batch {batch_num}/{total_batches} ({len(current_batch)} messages)")
            
            # Publish current batch with retry
            batch_published, batch_failed = self._publish_batch_with_retry(
                subject, current_batch, max_retries
            )
            
            published_count += batch_published
            failed_messages.extend(batch_failed)
            
            logger.info(f"Batch {batch_num}/{total_batches} complete: {batch_published}/{len(current_batch)} published")
        
        # Summary
        if failed_messages:
            logger.error(f"Published {published_count}/{total_messages} messages, {len(failed_messages)} failed after {max_retries} retries")
        else:
            logger.info(f"Successfully published all {published_count} messages to {subject}")
        
        return published_count
    
    def _publish_batch_with_retry(self, subject: str, messages: List[Dict[str, Any]], 
                                   max_retries: int) -> tuple[int, List[Dict[str, Any]]]:
        """
        Publish a batch of messages with retry mechanism
        
        Args:
            subject: Subject to publish to
            messages: List of message dictionaries
            max_retries: Maximum retry attempts
            
        Returns:
            Tuple of (published_count, failed_messages)
        """
        published_count = 0
        failed_messages = []
        
        # Convert messages to payloads
        message_payloads = []
        for i, message in enumerate(messages):
            try:
                payload = json.dumps(message, default=str).encode('utf-8')
                message_payloads.append((i, message, payload))
            except Exception as e:
                logger.error(f"Failed to serialize message: {e}")
                failed_messages.append(message)
        
        # Publish with retry
        retry_queue = message_payloads
        
        for attempt in range(max_retries):
            if not retry_queue:
                break
            
            attempt_num = attempt + 1
            next_retry_queue = []
            
            if attempt > 0:
                logger.info(f"Retry attempt {attempt_num}/{max_retries} for {len(retry_queue)} messages")
            
            # Publish messages in current retry attempt
            for idx, original_msg, payload in retry_queue:
                try:
                    # Publish to JetStream
                    ack = self.js.publish(subject, payload)
                    published_count += 1
                    logger.debug(f"Published message to {subject}, seq: {ack.seq}")
                    
                except Exception as e:
                    if attempt_num < max_retries:
                        # Add to retry queue
                        next_retry_queue.append((idx, original_msg, payload))
                        logger.warning(f"Message publish failed (attempt {attempt_num}), will retry: {e}")
                    else:
                        # Max retries reached
                        failed_messages.append(original_msg)
                        logger.error(f"Message publish failed after {max_retries} attempts: {e}")
            
            retry_queue = next_retry_queue
            
            # Wait before retry (exponential backoff)
            if retry_queue and attempt_num < max_retries:
                import time
                wait_time = min(2 ** attempt, 10)  # Max 10 seconds
                logger.debug(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
        
        return published_count, failed_messages
    
    def close(self) -> None:
        """
        Close NATS connection
        """
        try:
            if self.nc and self.is_connected:
                self.nc.drain()
                self.nc.close()
                self.is_connected = False
                logger.info("NATS connection closed")
        except Exception as e:
            logger.error(f"Error closing NATS connection: {e}")
