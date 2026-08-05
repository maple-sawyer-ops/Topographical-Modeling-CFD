"""
hyperlocal_logging.py

Shared logging setup for the HyperLocal WeatherXM Pro wind-data pull.

Call `setup_logging(LOG_DIR)` once, near the top of whichever script is
being run directly (e.g. in an `if __name__ == "__main__":` block) -- every
other module in this project gets its logger via
`logging.getLogger(__name__)`, and Python's `logging` module routes ALL of
those through whatever handlers this function attaches to the ROOT logger.
Modules never configure logging themselves, so there's exactly one place
this is set up.
"""

# Standard library only: `logging` does the actual work; `sys` gives us
# stdout for the console handler; `datetime` builds the timestamped
# filenames; `pathlib` creates the log directories if they don't exist yet;
# `json` serializes each log record to one JSON line for the JSON handler.
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Directory for the JSON-lines log output. Kept as a constant HERE (not in
# hyperlocal_input_loc.py / threaded through every caller as an extra
# argument) since it's an implementation detail of HOW this module logs, not
# something any other script needs to know or configure.
JSON_LOG_DIR = "./logs"


class _JsonLineFormatter(logging.Formatter):
    """
    A `logging.Formatter` subclass that renders each log record as ONE line
    of JSON (JSON Lines / `.jsonl` format), instead of the usual plain-text
    line.

    Functionality: subclassing `logging.Formatter` and overriding `format()`
    is the standard way to customise how a handler renders a `LogRecord` --
    every `Handler` calls `self.format(record)` internally, so swapping in
    this class changes ONLY the on-disk representation, not how logging
    calls are made anywhere else in the project.

    Syntax: `record.getMessage()` returns the message with any `%s`-style
    args already substituted in (e.g. `logger.info("found %d", 3)` becomes
    "found 3") -- using this instead of `record.msg` avoids re-implementing
    that substitution ourselves.
    """

    def format(self, record):
        # `self.formatTime(record, fmt)` is inherited from `logging.Formatter`
        # and turns the record's raw timestamp into a formatted string,
        # matching the plain-text handler's timestamp format.
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # `json.dumps(payload)` serializes the dict to a single-line JSON
        # string (no `indent=`) -- one JSON object per line is what makes
        # this "JSON Lines": each line is independently parseable, so a
        # reader can stream the file without waiting for it to close.
        return json.dumps(payload)


def setup_logging(log_dir):
    """
    Configure the ROOT logger to write every log message to a new
    timestamped plain-text file in `log_dir`, a new timestamped JSON-lines
    file in the module-level `JSON_LOG_DIR`, AND the console (stdout) --
    three handlers, one root logger, so every module's
    `logging.getLogger(__name__)` calls reach all three automatically.

    Returns
    -------
    tuple(pathlib.Path, pathlib.Path)
        (plain_text_log_file, json_log_file) -- the two files just created.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    Path(JSON_LOG_DIR).mkdir(parents=True, exist_ok=True)

    # Both filenames share one timestamp so a plain-text log and its JSON
    # counterpart from the same run are easy to pair up by name.
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = Path(log_dir) / ("%s.log" % timestamp)
    json_log_file = Path(JSON_LOG_DIR) / ("%s.jsonl" % timestamp)

    # `logging.getLogger()` with NO name returns the singleton ROOT logger --
    # every other logger in the process is a descendant of it.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Shared plain-text format for the file + console handlers.
    text_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # `FileHandler` writes every record to `log_file` on disk (plain text).
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(text_formatter)
    root_logger.addHandler(file_handler)

    # A second `FileHandler`, writing to a DIFFERENT file, formatted by
    # `_JsonLineFormatter` instead -- one JSON object per line.
    json_handler = logging.FileHandler(json_log_file, encoding="utf-8")
    json_handler.setFormatter(_JsonLineFormatter())
    root_logger.addHandler(json_handler)

    # `StreamHandler(sys.stdout)` writes every record to the console too,
    # so terminal output looks the same as it did with print() -- just
    # timestamped -- while ALSO landing in both files above.
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(text_formatter)
    root_logger.addHandler(console_handler)

    return log_file, json_log_file
