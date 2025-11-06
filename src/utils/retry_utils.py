"""
Retry Utilities
Robust retry mechanisms with exponential backoff for db_clients
"""

import logging
import asyncio
import time
from typing import Callable, TypeVar, Any, Optional, Tuple, Type
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF = 1.0  # seconds
DEFAULT_MAX_BACKOFF = 30.0  # seconds
DEFAULT_BACKOFF_MULTIPLIER = 2.0


class RetryConfig:
    """Configuration for retry behavior"""

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
        retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None
    ):
        """
        Initialize retry configuration

        Args:
            max_retries: Maximum number of retry attempts (0 = no retries)
            initial_backoff: Initial wait time in seconds before first retry
            max_backoff: Maximum wait time in seconds between retries
            backoff_multiplier: Multiplier for exponential backoff
            retryable_exceptions: Tuple of exception types to retry (None = retry all)
        """
        if max_retries < 0:
            raise ValueError(f"max_retries must be non-negative, got {max_retries}")
        if initial_backoff < 0:
            raise ValueError(f"initial_backoff must be non-negative, got {initial_backoff}")
        if max_backoff < initial_backoff:
            raise ValueError(f"max_backoff ({max_backoff}) must be >= initial_backoff ({initial_backoff})")
        if backoff_multiplier < 1:
            raise ValueError(f"backoff_multiplier must be >= 1, got {backoff_multiplier}")

        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier
        self.retryable_exceptions = retryable_exceptions

    def calculate_backoff(self, attempt: int) -> float:
        """
        Calculate backoff time for given attempt using exponential backoff

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Backoff time in seconds
        """
        backoff = self.initial_backoff * (self.backoff_multiplier ** attempt)
        return min(backoff, self.max_backoff)

    def is_retryable(self, exception: Exception) -> bool:
        """
        Check if exception is retryable

        Args:
            exception: Exception to check

        Returns:
            True if exception should be retried
        """
        if self.retryable_exceptions is None:
            return True
        return isinstance(exception, self.retryable_exceptions)


def retry_sync(config: RetryConfig):
    """
    Decorator for synchronous functions with retry logic

    Args:
        config: RetryConfig instance

    Example:
        @retry_sync(RetryConfig(max_retries=3, initial_backoff=1.0))
        def query_database(self, query: str):
            # Database query logic
            pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    # Check if exception is retryable
                    if not config.is_retryable(e):
                        logger.error(f"{func.__name__} failed with non-retryable exception: {e}")
                        raise

                    # Check if we have retries left
                    if attempt >= config.max_retries:
                        logger.error(
                            f"{func.__name__} failed after {config.max_retries + 1} attempts: {e}",
                            exc_info=True
                        )
                        raise

                    # Calculate backoff and retry
                    backoff = config.calculate_backoff(attempt)
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{config.max_retries + 1}): {e}. "
                        f"Retrying in {backoff:.2f}s..."
                    )
                    time.sleep(backoff)

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError(f"{func.__name__} failed with no exception captured")

        return wrapper
    return decorator


def retry_async(config: RetryConfig):
    """
    Decorator for async functions with retry logic

    Args:
        config: RetryConfig instance

    Example:
        @retry_async(RetryConfig(max_retries=3, initial_backoff=1.0))
        async def publish_message(self, subject: str, message: dict):
            # NATS publish logic
            pass
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    # Check if exception is retryable
                    if not config.is_retryable(e):
                        logger.error(f"{func.__name__} failed with non-retryable exception: {e}")
                        raise

                    # Check if we have retries left
                    if attempt >= config.max_retries:
                        logger.error(
                            f"{func.__name__} failed after {config.max_retries + 1} attempts: {e}",
                            exc_info=True
                        )
                        raise

                    # Calculate backoff and retry
                    backoff = config.calculate_backoff(attempt)
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{config.max_retries + 1}): {e}. "
                        f"Retrying in {backoff:.2f}s..."
                    )
                    await asyncio.sleep(backoff)

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError(f"{func.__name__} failed with no exception captured")

        return wrapper
    return decorator


def create_retry_config_from_dict(config_dict: dict) -> RetryConfig:
    """
    Create RetryConfig from configuration dictionary

    Args:
        config_dict: Dictionary with retry configuration keys:
            - max_retries: int
            - initial_backoff: float
            - max_backoff: float
            - backoff_multiplier: float

    Returns:
        RetryConfig instance
    """
    return RetryConfig(
        max_retries=config_dict.get('max_retries', DEFAULT_MAX_RETRIES),
        initial_backoff=config_dict.get('initial_backoff', DEFAULT_INITIAL_BACKOFF),
        max_backoff=config_dict.get('max_backoff', DEFAULT_MAX_BACKOFF),
        backoff_multiplier=config_dict.get('backoff_multiplier', DEFAULT_BACKOFF_MULTIPLIER)
    )
