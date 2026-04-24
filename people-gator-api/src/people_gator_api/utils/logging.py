import structlog
import logging
from opentelemetry import trace
from people_gator_api.utils.settings import settings

ALL_CALLSITE_PARAMETERS = list(structlog.processors.CallsiteParameter)

#def add_open_telemetry_spans(_, __, event_dict):
#    span = trace.get_current_span()
#    if not span.is_recording():
#        event_dict["span"] = None
#        return event_dict
#
#    ctx = span.get_span_context()
#    parent = getattr(span, "parent", None)
#
#    event_dict["span"] = {
#        "span_id": format(ctx.span_id, "016x"),
#        "trace_id": format(ctx.trace_id, "032x"),
#        "parent_span_id": None if not parent else format(parent.span_id, "016x"),
#    }
#
#    return event_dict

def configure_logging(otel_handler: logging.Handler | None = None):
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.ExtraAdder(),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.CallsiteParameterAdder(
            parameters=ALL_CALLSITE_PARAMETERS
        ),
        timestamper,
        #add_open_telemetry_spans,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    handlers: list[logging.Handler] = []
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    if otel_handler:
        otel_handler.setFormatter(formatter)
        handlers.append(otel_handler)
    
    logging.basicConfig(
        level={
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR
        }[settings.log_level],
        handlers=handlers,
        force=True,
    )
    
