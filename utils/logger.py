"""Logging configuration for the car service voice AI system."""

import logging
import sys
import os
from pathlib import Path
from typing import Optional
from config.settings import config


def setup_logger(name: str, call_sid: Optional[str] = None) -> logging.Logger:
    """
    Setup and configure logger with console and file handlers.

    Args:
        name: Logger name (usually __name__)
        call_sid: Optional call SID for context

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # File handler
    log_dir = Path(config.LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(config.LOG_FILE)
    file_handler.setLevel(logging.DEBUG)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


class ContextLogger:
    """Logger wrapper that adds contextual information to all log messages."""

    def __init__(self, logger: logging.Logger, **context):
        """
        Initialize context logger.

        Args:
            logger: Base logger instance
            **context: Context key-value pairs (e.g., call_sid, session_id)
        """
        self.logger = logger
        self.context = context

    def _format_message(self, msg: str) -> str:
        """Add context to message."""
        context_str = " ".join(f"[{k}={v}]" for k, v in self.context.items() if v)
        return f"{context_str} {msg}" if context_str else msg

    def debug(self, msg: str, *args, **kwargs):
        """Log debug message with context."""
        self.logger.debug(self._format_message(msg), *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        """Log info message with context."""
        self.logger.info(self._format_message(msg), *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """Log warning message with context."""
        self.logger.warning(self._format_message(msg), *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        """Log error message with context."""
        self.logger.error(self._format_message(msg), *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        """Log critical message with context."""
        self.logger.critical(self._format_message(msg), *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs):
        """Log exception with context."""
        self.logger.exception(self._format_message(msg), *args, **kwargs)
