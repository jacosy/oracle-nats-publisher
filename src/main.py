"""
Main Publisher Application
Simple orchestration with layered architecture using async/await
"""

import logging
import signal
import sys
import asyncio
from typing import Dict, Any, Optional

from db_clients.oracle_db_client import OracleDbClient
from db_clients.mariadb_db_client import MariaDbClient
from repositories.oracle_repository import OracleRepository
from repositories.mariadb_repository import MariaDbRepository
from services.polling_service import PollingService
from publishers.txlog_event_publisher import TxLogEventPublisher
from config.config_loader import ConfigLoader

logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_RECORDS = 10000
DEFAULT_MAX_RETRIES = 3
RETRY_SLEEP_SECONDS = 5


class PublisherApp:
    """
    Main application - pure orchestration
    No business logic, just coordinates components
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize application with layered architecture"""
        self.config = config
        self.running = False

        # Layer 1: Pure CRUD clients
        oracle_db_client = OracleDbClient(config['oracle_db'])
        mariadb_db_client = MariaDbClient(config['mariadb'])

        # Layer 2: Repositories (data access patterns)
        oracle_repo = OracleRepository(oracle_db_client)
        mariadb_repo = MariaDbRepository(mariadb_db_client)

        # Publishers (TxLog business logic layer)
        txlog_publisher = TxLogEventPublisher(config)

        # Layer 3: Business logic service (now includes publishing)
        # Service will handle graceful shutdown of all layers
        self.polling_service = PollingService(oracle_repo, mariadb_repo, txlog_publisher)

        # Configuration
        publisher_config = config['publisher']
        self.program_name: str = publisher_config['program_name']
        self.poll_interval: int = publisher_config['poll_interval']
        self.batch_size: int = publisher_config.get('batch_size', DEFAULT_BATCH_SIZE)
        self.max_records: int = publisher_config.get('max_records_per_run', DEFAULT_MAX_RECORDS)
        self.max_retries: int = publisher_config.get('max_retries', DEFAULT_MAX_RETRIES)

        self.setup_signal_handlers()
    
    def setup_signal_handlers(self) -> None:
        """Setup graceful shutdown"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Optional[Any]) -> None:
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    async def initialize(self) -> None:
        """
        Initialize application and connect to NATS

        Raises:
            Exception: If initialization fails (connection timeout, auth failure, etc.)
        """
        logger.info("Initializing publisher application...")

        try:
            # Connect to NATS via service layer (with timeout)
            connection_timeout = self.config.get('nats', {}).get('connect_timeout', 30)
            await self.polling_service.txlog_publisher.connect(timeout=connection_timeout)

            # Initialize program tracking
            self.polling_service.initialize_program(self.program_name)

            logger.info("Initialization complete")

        except asyncio.TimeoutError:
            logger.error("Initialization failed: NATS connection timed out")
            raise
        except Exception as e:
            logger.error(f"Initialization failed: {e}", exc_info=True)
            raise

    async def process_one_cycle(self) -> bool:
        """
        Process one polling cycle - delegates everything to service

        Returns:
            True if successful, False otherwise
        """
        try:
            # Service handles: fetch → publish → track (async)
            published_count = await self.polling_service.poll_and_publish(
                self.program_name,
                self.max_records,
                self.batch_size,
                self.max_retries
            )

            if published_count > 0:
                logger.info(f"Cycle completed: {published_count} records published")
                return True
            else:
                logger.info("Cycle completed: No new records")
                return True

        except Exception as e:
            logger.error(f"Cycle failed: {e}", exc_info=True)
            return False

    async def run(self) -> None:
        """
        Main async run loop

        Handles initialization failure and ensures cleanup even if
        shutdown signal arrives during initialization.
        """
        self.running = True
        initialized = False

        try:
            # Initialize with timeout - if signal arrives during init, it will be handled
            await self.initialize()
            initialized = True

            # Check if shutdown was requested during initialization
            if not self.running:
                logger.warning("Shutdown requested during initialization, exiting...")
                return

            logger.info(f"Starting polling loop with {self.poll_interval}s interval")

            while self.running:
                try:
                    success = await self.process_one_cycle()

                    if success:
                        logger.info(f"Sleeping for {self.poll_interval} seconds...")
                        # Sleep in small increments for responsive shutdown
                        for _ in range(self.poll_interval):
                            if not self.running:
                                break
                            await asyncio.sleep(1)
                    else:
                        logger.warning("Cycle failed, will retry after brief pause")
                        await asyncio.sleep(RETRY_SLEEP_SECONDS)

                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt received")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)
                    await asyncio.sleep(RETRY_SLEEP_SECONDS)

        except Exception as init_error:
            logger.error(f"Failed to initialize application: {init_error}", exc_info=True)
            # Don't re-raise - we want to clean up what was partially initialized

        finally:
            # Clean up only if something was initialized
            # If initialization failed early, there may be nothing to clean
            if initialized or self.polling_service:
                await self.cleanup()
            else:
                logger.info("No resources to clean up (initialization failed early)")

    async def cleanup(self) -> None:
        """
        Cleanup resources gracefully through service layer

        Graceful shutdown order:
        1. Stop accepting new work (self.running = False, already done)
        2. Wait for current cycle to complete (handled by main loop)
        3. Close service (which cascades to publisher and repositories)

        This prevents interrupting in-flight operations and ensures:
        - NATS messages are fully published
        - Database transactions are completed
        - Connections are properly closed
        """
        logger.info("Starting graceful shutdown...")

        try:
            # Close service layer - it will cascade to all underlying layers
            await self.polling_service.close()
            logger.info("All resources closed successfully")
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}", exc_info=True)

        logger.info("Graceful shutdown completed")


def setup_logging(config: Dict[str, Any]) -> None:
    """Setup logging configuration"""
    log_config = config.get('logging', {})
    log_level = log_config.get('level', 'INFO').upper()
    log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Validate log level
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    if log_level not in valid_levels:
        print(f"Warning: Invalid log level '{log_level}', defaulting to INFO")
        log_level = 'INFO'

    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format
    )


async def async_main() -> None:
    """Async main entry point"""
    # Load configuration
    config = ConfigLoader.load_config()

    # Setup logging
    setup_logging(config)

    logger.info("=" * 80)
    logger.info("Oracle NATS Publisher - Starting (Async Mode)")
    logger.info("=" * 80)

    # Create and run application
    app = PublisherApp(config)
    await app.run()

    logger.info("Publisher stopped")


def main() -> None:
    """Main entry point - runs async event loop"""
    try:
        # Run async main in event loop
        asyncio.run(async_main())
        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
