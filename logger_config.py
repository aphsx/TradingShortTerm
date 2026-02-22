"""
Centralized logging configuration for the trading bot.

Provides structured logging with:
- Console output for development
- File rotation for production
- Separate log levels per component
- Performance-optimized formatters
"""

import logging
import logging.handlers
import sys
from pathlib import Path

# Create logs directory if it doesn't exist
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# Log format
DETAILED_FORMAT = logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

SIMPLE_FORMAT = logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)


def setup_logging(level=logging.INFO, console_level=logging.INFO):
    """
    Configure logging for the entire application.

    Args:
        level: File logging level (default: INFO)
        console_level: Console logging level (default: INFO)
    """
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything, filter at handler level

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # === Console Handler (for real-time monitoring) ===
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(SIMPLE_FORMAT)
    root_logger.addHandler(console_handler)

    # === Main Application Log (rotating file) ===
    main_handler = logging.handlers.RotatingFileHandler(
        LOGS_DIR / "bot.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    main_handler.setLevel(level)
    main_handler.setFormatter(DETAILED_FORMAT)
    root_logger.addHandler(main_handler)

    # === Order Log (separate file for audit trail) ===
    order_logger = logging.getLogger("orders")
    order_handler = logging.handlers.RotatingFileHandler(
        LOGS_DIR / "orders.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=10,  # Keep more order history
        encoding='utf-8'
    )
    order_handler.setLevel(logging.INFO)
    order_handler.setFormatter(DETAILED_FORMAT)
    order_logger.addHandler(order_handler)
    order_logger.propagate = False  # Don't send to root logger

    # === Error Log (critical issues only) ===
    error_handler = logging.handlers.RotatingFileHandler(
        LOGS_DIR / "errors.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(DETAILED_FORMAT)
    root_logger.addHandler(error_handler)

    # === Reduce noise from external libraries ===
    logging.getLogger("ccxt").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    logging.info("=" * 80)
    logging.info("🚀 Logging system initialized")
    logging.info(f"📁 Log directory: {LOGS_DIR.absolute()}")
    logging.info(f"📊 Console level: {logging.getLevelName(console_level)}")
    logging.info(f"📄 File level: {logging.getLevelName(level)}")
    logging.info("=" * 80)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.

    Args:
        name: Logger name (typically __name__)

    Returns:
        logging.Logger: Configured logger instance
    """
    return logging.getLogger(name)
