"""
NATS Client
Low-level NATS connection and operations (CRUD only)
"""

import logging
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
import nats
from nats.aio.client import Client as NATSClient
from nats.js import JetStreamContext
from nats.js.api import StreamConfig

logger = logging.getLogger(__name__)

# Constants
MAX_BACKOFF_SECONDS = 10  # Maximum wait time between retries


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

        self.nc: Optional[NATSClient] = None
        self.js: Optional[JetStreamContext] = None
        self.is_connected = False

        logger.info(f"NATS Client initialized for {self.servers}")
    
    async def connect(self) -> None:
        """
        Connect to NATS server and initialize JetStream

        Raises:
            Exception: If connection fails
        """
        try:
            # Build connection options
            connect_opts = {
                'servers': self.servers,
                'max_reconnect_attempts': self.config.get('max_reconnect_attempts', 60),
                'reconnect_time_wait': self.config.get('reconnect_time_wait', 2)
            }

            # Add authentication if provided
            if self.username and self.password:
                connect_opts['user'] = self.username
                connect_opts['password'] = self.password

            # Connect to NATS (async)
            self.nc = await nats.connect(**connect_opts)

            logger.info(f"Connected to NATS at {self.servers}")

            # Get JetStream context
            self.js = self.nc.jetstream()

            self.is_connected = True
            logger.info("JetStream initialized")

        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}", exc_info=True)
            raise
    
    async def ensure_stream(self, stream_name: str, subjects: List[str]) -> None:
        """
        Ensure JetStream stream exists, create if not

        Args:
            stream_name: Name of the stream
            subjects: List of subjects for the stream
        """
        if not self.js:
            raise RuntimeError("Not connected to NATS JetStream")

        try:
            # Try to get stream info
            await self.js.stream_info(stream_name)
            logger.info(f"Stream {stream_name} already exists")
        except Exception:
            # Stream doesn't exist, create it
            try:
                config = StreamConfig(
                    name=stream_name,
                    subjects=subjects,
                    description=f"Stream for {', '.join(subjects)}"
                )

                await self.js.add_stream(config)
                logger.info(f"Created stream: {stream_name} with subjects: {subjects}")
            except Exception as e:
                logger.warning(f"Could not create stream {stream_name}: {e}")
    
    async def publish(self, subject: str, message: Dict[str, Any]) -> bool:
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
            ack = await self.js.publish(subject, payload)

            logger.debug(f"Published to {subject}, seq: {ack.seq}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish to {subject}: {e}", exc_info=True)
            return False
    
    async def publish_batch(self, subject: str, messages: List[Dict[str, Any]],
                           batch_size: int = 100, max_retries: int = 3) -> int:
        """
        Publish batch of messages to NATS JetStream with TRUE async batch publishing

        Uses NATS publish_async() to send multiple messages concurrently for maximum
        throughput. Messages are sent in batches and awaited together using asyncio.gather().

        Args:
            subject: Subject to publish to
            messages: List of message dictionaries
            batch_size: Number of messages to publish concurrently per batch (default: 100)
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

        logger.info(f"Publishing {total_messages} messages in async batches of {batch_size} (max_retries={max_retries})")

        # Pre-serialize all messages to catch format errors early
        serialized_messages = []
        for i, message in enumerate(messages):
            try:
                payload = json.dumps(message, default=str).encode('utf-8')
                serialized_messages.append((i, message, payload))
            except Exception as e:
                logger.error(f"Failed to serialize message {i+1}/{total_messages}: {e}")
                failed_messages.append(message)

        if not serialized_messages:
            logger.error("No valid messages to publish after serialization")
            return 0

        logger.info(f"Serialized {len(serialized_messages)}/{total_messages} messages successfully")

        # Process in batches
        total_batches = (len(serialized_messages) + batch_size - 1) // batch_size

        for batch_start in range(0, len(serialized_messages), batch_size):
            batch_end = min(batch_start + batch_size, len(serialized_messages))
            current_batch = serialized_messages[batch_start:batch_end]

            batch_num = (batch_start // batch_size) + 1

            logger.debug(f"Processing batch {batch_num}/{total_batches} ({len(current_batch)} messages)")

            # Publish current batch with retry (async)
            batch_published, batch_failed = await self._publish_batch_async_with_retry(
                subject, current_batch, max_retries
            )

            published_count += batch_published
            failed_messages.extend(batch_failed)

            success_rate = (batch_published / len(current_batch)) * 100
            logger.info(f"Batch {batch_num}/{total_batches} complete: {batch_published}/{len(current_batch)} published ({success_rate:.1f}%)")

        # Summary
        if failed_messages:
            failure_rate = (len(failed_messages) / total_messages) * 100
            logger.error(f"Published {published_count}/{total_messages} messages, {len(failed_messages)} failed ({failure_rate:.1f}% failure rate)")
        else:
            logger.info(f"Successfully published all {published_count} messages to {subject}")

        return published_count

    async def _publish_batch_async_with_retry(
        self,
        subject: str,
        serialized_messages: List[Tuple[int, Dict[str, Any], bytes]],
        max_retries: int
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Publish a batch of pre-serialized messages using async batch publishing with retry

        Uses asyncio.gather() to publish all messages in the batch concurrently for
        maximum throughput. Failed messages are retried with exponential backoff.

        Args:
            subject: Subject to publish to
            serialized_messages: List of tuples (index, original_message, payload)
            max_retries: Maximum retry attempts

        Returns:
            Tuple of (published_count, failed_messages)
        """
        if not self.js:
            raise RuntimeError("Not connected to NATS JetStream")

        published_count = 0
        failed_messages = []
        retry_queue = serialized_messages

        for attempt in range(max_retries):
            if not retry_queue:
                break

            attempt_num = attempt + 1

            if attempt > 0:
                logger.info(f"Retry attempt {attempt_num}/{max_retries} for {len(retry_queue)} messages")

            # Create async publish tasks for all messages in batch
            publish_tasks = [self._publish_single_async(subject, payload) for _, _, payload in retry_queue]

            # Execute all publishes concurrently
            results = await asyncio.gather(*publish_tasks, return_exceptions=True)

            # Process results
            next_retry_queue = []
            for (idx, original_msg, payload), result in zip(retry_queue, results):
                if isinstance(result, Exception):
                    # Publish failed
                    if attempt_num < max_retries:
                        # Add to retry queue
                        next_retry_queue.append((idx, original_msg, payload))
                        logger.warning(f"Message {idx+1} publish failed (attempt {attempt_num}/{max_retries}): {result}")
                    else:
                        # Max retries reached
                        failed_messages.append(original_msg)
                        logger.error(f"Message {idx+1} publish failed after {max_retries} attempts: {result}")
                else:
                    # Publish succeeded
                    published_count += 1
                    logger.debug(f"Published message {idx+1} to {subject}, seq: {result}")

            retry_queue = next_retry_queue

            # Wait before retry with exponential backoff
            if retry_queue and attempt_num < max_retries:
                wait_time = min(2 ** attempt, MAX_BACKOFF_SECONDS)
                logger.info(f"Waiting {wait_time}s before retry attempt {attempt_num + 1}...")
                await asyncio.sleep(wait_time)

        return published_count, failed_messages

    async def _publish_single_async(self, subject: str, payload: bytes) -> int:
        """
        Publish a single message asynchronously

        Args:
            subject: Subject to publish to
            payload: Pre-serialized message payload

        Returns:
            Sequence number from ack

        Raises:
            Exception: If publish fails
        """
        if not self.js:
            raise RuntimeError("Not connected to NATS JetStream")

        ack = await self.js.publish(subject, payload)
        return ack.seq
    
    async def close(self) -> None:
        """
        Close NATS connection
        """
        try:
            if self.nc is not None and self.is_connected:
                await self.nc.drain()
                await self.nc.close()
                self.is_connected = False
                logger.info("NATS connection closed")
        except Exception as e:
            logger.error(f"Error closing NATS connection: {e}")
