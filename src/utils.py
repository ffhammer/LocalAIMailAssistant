from enum import StrEnum

from loguru import logger
from result import Err


class LogLevel(StrEnum):
    info = "INFO"
    debug = "DEBUG"
    warning = "WARNING"
    error = "ERROR"


LOG_FUNC = {
    LogLevel.info: logger.info,
    LogLevel.debug: logger.debug,
    LogLevel.warning: logger.warning,
    LogLevel.error: logger.error,
}


def return_error_and_log(message: str, level: LogLevel = LogLevel.error) -> Err:
    LOG_FUNC[level](message)
    return Err(message)
