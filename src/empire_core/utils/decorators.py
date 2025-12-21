import asyncio
import functools
import logging
from typing import Callable, Optional, Tuple, Type


def handle_errors(
    logger: Optional[logging.Logger] = None,
    log_msg: Optional[str] = None,
    re_raise: bool = True,
    cleanup_method: Optional[str] = None,
    ignore: Optional[Tuple[Type[BaseException], ...]] = None,
):
    """
    Decorator to centralize error handling, logging, and cleanup.

    Args:
        logger: The logger instance to use. If None, tries to get 'logger' from instance or module.
        log_msg: Custom message to prefix the error log with.
        re_raise: Whether to re-raise the caught exception.
        cleanup_method: Name of a method on 'self' to call if an exception occurs (for instance methods).
        ignore: Tuple of exception types to ignore (not log as error, just debug/pass).
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Determine logger
            _logger = logger
            if _logger is None:
                # Try to get 'self.logger' or module level logger
                if args and hasattr(args[0], "logger"):
                    _logger = args[0].logger
                else:
                    _logger = logging.getLogger(func.__module__)

            try:
                return await func(*args, **kwargs)
            except asyncio.CancelledError as e:
                # CancelledError is usually control flow, maybe just re-raise
                if ignore and asyncio.CancelledError in ignore:
                    pass
                else:
                    _logger.debug(f"{func.__name__} cancelled.")
                raise e
            except Exception as e:
                if ignore and isinstance(e, ignore):
                    _logger.debug(f"Ignored error in {func.__name__}: {e}")
                    return

                msg = log_msg or f"Error in {func.__name__}"
                _logger.error(f"{msg}: {e}", exc_info=True)

                # Cleanup logic
                if cleanup_method and args:
                    self_obj = args[0]
                    if hasattr(self_obj, cleanup_method):
                        cleanup = getattr(self_obj, cleanup_method)
                        if asyncio.iscoroutinefunction(cleanup):
                            await cleanup()
                        else:
                            cleanup()

                if re_raise:
                    raise e

        return wrapper

    return decorator
