import logging
import logging
import os
from logging.handlers import RotatingFileHandler
from config.config import load_config_from_json, BASE_DIR
config = load_config_from_json()
level = logging.INFO
if config.get('log_level') == 'DEBUG':
    level = logging.DEBUG
elif config.get('log_level') == 'INFO':
    level = logging.INFO
elif config.get('log_level') == 'ERROR':
    level = logging.ERROR
if level == logging.DEBUG:
    logging.basicConfig(level=logging.DEBUG)
# Define absolute path for the logs directory relative to the project structure
# bot/utils/logger.py -> bot/logs
DEFAULT_LOG_DIR = os.path.join(BASE_DIR, 'logs')


def setup_logger(name: str = "bot_logger", log_dir: str = DEFAULT_LOG_DIR, level: int = level) -> logging.Logger:
    """
    Initializes and returns a logger that writes to both console and a log file.

    Args:
        name: Name of the logger.
        log_dir: Directory to store log files. Defaults to bot/logs.
        level: Logging level. Defaults to logging.INFO.

    Returns:
        logging.Logger: Configured logger instance.
    """
    # Create logs directory if it doesn't exist
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding multiple handlers if the logger is already configured
    if not logger.handlers:
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)

        # Create file handler (with rotation, max 5MB per file, keep 5 backups)
        log_file = os.path.join(log_dir, f"{name}.log")
        try:
            file_handler = RotatingFileHandler(
                log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8'
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Failed to setup file handler for logger: {e}")

        # Add handlers to logger
        logger.addHandler(console_handler)

    return logger


# Create a default logger instance that can be imported directly
logger = setup_logger()
