"""
Repositories Layer - Data Access Patterns
Business-specific queries, uses db_clients
"""

from .oracle_repository import OracleRepository
from .mariadb_repository import MariaDbRepository

__all__ = ['OracleRepository', 'MariaDbRepository']
