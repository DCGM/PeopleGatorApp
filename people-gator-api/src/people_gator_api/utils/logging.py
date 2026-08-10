import structlog
import logging
from datetime import (
    datetime,
    timezone,
)
from people_gator_api.settings import settings

ALL_CALLSITE_PARAMETERS = list(structlog.processors.CallsiteParameter)


def configure_logging():
    handlers: list[logging.Handler] = []

    class Iso8601Formatter(logging.Formatter):
        """Formatter that uses ISO-8601 timestamps in UTC with milliseconds.

        Example: 2026-05-21T14:30:00.123+00:00
        """

        def formatTime(
            self, record: logging.LogRecord, datefmt: str | None = None
        ) -> str:
            dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
            return dt.isoformat(timespec="milliseconds")

    fmt = (
        "%(asctime)s %(levelname)s %(name)s %(module)s:%(lineno)d "
        "[pid:%(process)d tid:%(thread)d] %(message)s"
    )
    formatter = Iso8601Formatter(fmt=fmt)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    # if otel_handler:
    #     otel_handler.setFormatter(formatter)
    #     handlers.append(otel_handler)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True,
    )
