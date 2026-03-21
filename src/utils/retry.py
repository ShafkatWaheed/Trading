"""Retry decorator with exponential backoff."""

import functools
import time
from typing import Callable, TypeVar

from src.utils.db import log_api_call

T = TypeVar("T")


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    source: str = "unknown",
) -> Callable:
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt == max_retries:
                        log_api_call(source, fn.__name__, "error", f"Failed after {max_retries} retries: {e}")
                        raise
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    log_api_call(source, fn.__name__, "retry", f"Attempt {attempt + 1}/{max_retries}: {e}")
                    time.sleep(delay)
            raise last_exc  # unreachable but satisfies type checker
        return wrapper
    return decorator
