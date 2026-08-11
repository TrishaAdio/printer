"""Rotating file log plus console echo.

A packaged windowed exe has no console, so the log file is the only way to
diagnose a driver that misbehaves on a user's machine. Keep it cheap and always on.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys

from . import env

_CONFIGURED = False


def setup(level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("glassprint")
    if _CONFIGURED:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            env.log_dir() / "glassprint.log",
            maxBytes=1_500_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
    except OSError:
        pass

    if sys.stderr is not None:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(fmt)
        stream.setLevel(level)
        logger.addHandler(stream)

    _CONFIGURED = True
    logger.info("logging started (simulated=%s frozen=%s)", env.SIMULATED, env.IS_FROZEN)
    return logger


def get(name: str = "") -> logging.Logger:
    setup()
    return logging.getLogger("glassprint" + (f".{name}" if name else ""))
