"""
Configuration Loader
Handles loading configuration from files and environment variables
"""

import os
import yaml
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Load and merge configuration from multiple sources"""
    
    @staticmethod
    def load_config(config_path: str = None) -> Dict[str, Any]:
        """
        Load configuration with priority: ENV > config.yaml
        
        Args:
            config_path: Path to config file (default: ../config/config.yaml)
            
        Returns:
            Merged configuration dictionary
        """
        # Default config path
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'config',
                'config.yaml'
            )
        
        # Start with defaults
        config = ConfigLoader._get_default_config()
        
        # Load from YAML file if exists
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    config = ConfigLoader._merge_dicts(config, file_config)
                    logger.info(f"Loaded config from {config_path}")
        else:
            logger.warning(f"Config file not found: {config_path}, using defaults")
        
        # Override with environment variables
        config = ConfigLoader._apply_env_overrides(config)
        
        return config
    
    @staticmethod
    def _get_default_config() -> Dict[str, Any]:
        """Get default configuration"""
        return {
            'oracle_db': {
                'user': 'oracle_user',
                'password': 'oracle_password',
                'dsn': 'localhost:1521/ORCL',
                'pool_min': 1,
                'pool_max': 5
            },
            'mariadb': {
                'host': 'localhost',
                'port': 3306,
                'database': 'intime',
                'user': 'mariadb_user',
                'password': 'mariadb_password',
                'pool_size': 5
            },
            'nats': {
                'servers': ['nats://localhost:4222'],
                'topic': 'intime.txlog.event',
                'connect_timeout': 10,
                'max_reconnect_attempts': 60,
                'reconnect_time_wait': 2
            },
            'publisher': {
                'program_name': 'M_INTIMECASEAGENT',
                'poll_interval': 60,
                'batch_size': 100,
                'max_records_per_run': 10000
            },
            'logging': {
                'level': 'INFO',
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            }
        }
    
    @staticmethod
    def _merge_dicts(base: Dict, override: Dict) -> Dict:
        """Recursively merge two dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigLoader._merge_dicts(result[key], value)
            else:
                result[key] = value
        return result
    
    @staticmethod
    def _apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides"""
        
        # Oracle overrides
        if os.getenv('ORACLE_USER'):
            config['oracle_db']['user'] = os.getenv('ORACLE_USER')
        if os.getenv('ORACLE_PASSWORD'):
            config['oracle_db']['password'] = os.getenv('ORACLE_PASSWORD')
        if os.getenv('ORACLE_DSN'):
            config['oracle_db']['dsn'] = os.getenv('ORACLE_DSN')
        
        # MariaDB overrides
        if os.getenv('MARIADB_HOST'):
            config['mariadb']['host'] = os.getenv('MARIADB_HOST')
        if os.getenv('MARIADB_PORT'):
            config['mariadb']['port'] = int(os.getenv('MARIADB_PORT'))
        if os.getenv('MARIADB_DATABASE'):
            config['mariadb']['database'] = os.getenv('MARIADB_DATABASE')
        if os.getenv('MARIADB_USER'):
            config['mariadb']['user'] = os.getenv('MARIADB_USER')
        if os.getenv('MARIADB_PASSWORD'):
            config['mariadb']['password'] = os.getenv('MARIADB_PASSWORD')
        
        # NATS overrides
        if os.getenv('NATS_SERVERS'):
            config['nats']['servers'] = os.getenv('NATS_SERVERS').split(',')
        if os.getenv('NATS_TOPIC'):
            config['nats']['topic'] = os.getenv('NATS_TOPIC')
        
        # Publisher overrides
        if os.getenv('PROGRAM_NAME'):
            config['publisher']['program_name'] = os.getenv('PROGRAM_NAME')
        if os.getenv('POLL_INTERVAL'):
            config['publisher']['poll_interval'] = int(os.getenv('POLL_INTERVAL'))
        if os.getenv('BATCH_SIZE'):
            config['publisher']['batch_size'] = int(os.getenv('BATCH_SIZE'))
        if os.getenv('MAX_RECORDS_PER_RUN'):
            config['publisher']['max_records_per_run'] = int(os.getenv('MAX_RECORDS_PER_RUN'))
        
        # Logging overrides
        if os.getenv('LOG_LEVEL'):
            config['logging']['level'] = os.getenv('LOG_LEVEL')
        
        return config
