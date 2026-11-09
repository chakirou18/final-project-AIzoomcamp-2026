"""Start Uvicorn with JSON logging from the first server log record."""

import logging

import uvicorn

from fieldops.logging import configure_logging
from fieldops.settings import Settings


def main() -> None:
    configure_logging("local", "INFO")
    try:
        settings = Settings()
        configure_logging(settings.environment, settings.log_level)
    except ValueError as error:
        logging.getLogger("fieldops.startup").error(
            "configuration_invalid", extra={"error_type": type(error).__name__}
        )
        raise SystemExit(1) from None
    uvicorn.run("fieldops.main:app", host="0.0.0.0", port=8000, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
