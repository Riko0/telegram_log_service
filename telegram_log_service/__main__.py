"""Allow running the service with `python -m telegram_log_service`."""

import asyncio
import sys
import logging

from telegram_log_service.main import main, logger


def cli():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt. Shutting down.")
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception as e:
        logger.error(f"Startup error: {e}", exc_info=True)
        sys.stdout.flush()
        sys.stderr.flush()


if __name__ == "__main__":
    cli()
