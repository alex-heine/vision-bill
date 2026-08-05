import logging
import logging.config

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s | %(levelname)-8s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "access": {
            "format": "%(asctime)s | ACCESS | %(client_addr)s | %(request_line)s | %(status_code)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        # Your app's root namespace
        "app": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "routers": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        # Take over Uvicorn's loggers
        "uvicorn": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    # Catch-all for anything not explicitly configured above
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

def setup_logging():
    logging.config.dictConfig(LOGGING_CONFIG)
