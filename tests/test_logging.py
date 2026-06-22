import json
import logging
import pytest
from io import StringIO

from src.logging_config import setup_logging, get_logger


def test_structured_log_output():
    """Logs should be JSON with timestamp, level, message, and module."""
    stream = StringIO()
    setup_logging(stream=stream, level=logging.INFO)
    logger = get_logger("test")
    logger.info("test message", extra={"patient_id": "P001"})

    stream.seek(0)
    line = stream.readline()
    data = json.loads(line)
    assert data["message"] == "test message"
    assert data["level"] == "INFO"
    assert data["module"] == "test"
    assert "timestamp" in data
    assert data["patient_id"] == "P001"


def test_get_logger_returns_named_logger():
    logger = get_logger("my_module")
    assert logger.name == "my_module"


def test_structured_log_with_request_id():
    stream = StringIO()
    setup_logging(stream=stream, level=logging.INFO)
    logger = get_logger("api")
    logger.info("handling request", extra={"request_id": "abc123"})

    stream.seek(0)
    data = json.loads(stream.readline())
    assert data["request_id"] == "abc123"


def test_structured_log_with_exception():
    stream = StringIO()
    setup_logging(stream=stream, level=logging.ERROR)
    logger = get_logger("test")
    try:
        raise ValueError("something broke")
    except ValueError:
        logger.error("caught error", exc_info=True)

    stream.seek(0)
    data = json.loads(stream.readline())
    assert data["level"] == "ERROR"
    assert "something broke" in data["exception"]
