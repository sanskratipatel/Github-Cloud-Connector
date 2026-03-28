import sys
from loguru import logger


def setup_logger(debug: bool = False) -> None:
    logger.remove()

    log_level = "DEBUG" if debug else "INFO"
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    logger.add(sys.stdout, level=log_level, format=log_format, colorize=True)
    logger.add(
        "logs/app.log",
        level="INFO",
        format=log_format,
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        colorize=False,
    )


__all__ = ["logger", "setup_logger"]
