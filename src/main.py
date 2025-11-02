"""
Main Publisher Application
Simple orchestration with layered architecture
"""

import logging
import signal
import sys
import time
from typing import Dict, Any

from db_clients.oracle_db_client import OracleDbClient
from db_clients.mariadb_db_client import MariaDbClient
from repositories.oracle_repository import OracleRepository
from repositories.mariadb_repository import MariaDbRepository
from services.polling_service import PollingService
from publishers.txlog_event_publisher import TxLogEventPublisher
from config.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class PublisherApp:
    """
    Main application - pure orchestration
    No business logic, just coordinates components
    """
    
    def __init__(self, config: Dict[str, Any]):
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
        self.polling_service = PollingService(oracle_repo, mariadb_repo, txlog_publisher)
        
        # Configuration
        self.program_name = config['publisher']['program_name']
        self.poll_interval = config['publisher']['poll_interval']
        self.batch_size = config['publisher'].get('batch_size', 100)
        self.max_records = config['publisher'].get('max_records_per_run', 10000)
        self.max_retries = config['publisher'].get('max_retries', 3)
        
        self.setup_signal_handlers()
    
    def setup_signal_handlers(self):
        """Setup graceful shutdown"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def initialize(self):
        """Initialize application"""
        logger.info("Initializing publisher application...")
        
        # Initialize program tracking
        self.polling_service.initialize_program(self.program_name)
        
        logger.info("Initialization complete")
    
    def process_one_cycle(self) -> bool:
        """
        Process one polling cycle - delegates everything to service
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Service handles: fetch → publish → track
            published_count = self.polling_service.poll_and_publish(
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
    
    def run(self):
        """Main run loop"""
        self.running = True
        
        try:
            self.initialize()
            
            logger.info(f"Starting polling loop with {self.poll_interval}s interval")
            
            while self.running:
                try:
                    success = self.process_one_cycle()
                    
                    if success:
                        logger.info(f"Sleeping for {self.poll_interval} seconds...")
                        # Sleep in small increments for responsive shutdown
                        for _ in range(self.poll_interval):
                            if not self.running:
                                break
                            time.sleep(1)
                    else:
                        logger.warning("Cycle failed, will retry after brief pause")
                        time.sleep(5)
                        
                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt received")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)
                    time.sleep(5)
                    
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up resources...")
        logger.info("Cleanup completed")


def setup_logging(config: Dict[str, Any]):
    """Setup logging configuration"""
    log_config = config.get('logging', {})
    log_level = log_config.get('level', 'INFO')
    log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format
    )


def main():
    """Main entry point"""
    try:
        # Load configuration
        config = ConfigLoader.load_config()
        
        # Setup logging
        setup_logging(config)
        
        logger.info("=" * 80)
        logger.info("Oracle NATS Publisher - Starting")
        logger.info("=" * 80)
        
        # Create and run application
        app = PublisherApp(config)
        app.run()
        
        logger.info("Publisher stopped")
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
