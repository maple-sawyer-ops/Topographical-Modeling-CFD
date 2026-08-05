"""
synoptic_logging.py

Shared logging setup for the HyperLocal Synoptic wind-data pull. Mirrors
hyperlocal_logging.py from the WeatherXM pipeline (see
"HyperLocal Data WeatherXM/hyperlocal_logging.py") so the two providers are
easy to compare side by side.

Call `setup_logging(LOG_DIR)` once, in the `__main__` block of whichever
script is run directly -- every other module gets its logger via
`logging.getLogger(__name__)` and those propagate up to the handlers this
attaches to the root logger.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path


def setup_logging(log_dir):
    """Attach a file handler (log_dir/{timestamp}.log) and a console handler
    to the ROOT logger. Returns the log file path."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = Path(log_dir) / ("%s.log" % timestamp)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    return log_file
