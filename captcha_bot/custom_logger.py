# SPDX-FileCopyrightText: 2026 Firdaus Hakimi <hakimifirdaus944@gmail.com>
# SPDX-License-Identifier: Apache-2.0

import datetime
import inspect
import logging
import queue
import re
import threading
from dataclasses import dataclass
from logging import LogRecord
from logging.handlers import QueueHandler

from rich.console import Console
from rich.markup import escape
from rich.text import Text

lg: logging.Logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)


@dataclass(frozen=True)
class CalleeInfo:
    module_name: str
    fn_name: str
    file: str
    lineno: int


class CustomLogger:
    def __init__(self) -> None:
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.queue = queue.Queue()
        self.console = Console(force_terminal=True, soft_wrap=True)

        self.thread.start()
        lg.info("logger thread started")

        self.level_colour: dict[int, str] = {
            logging.DEBUG: "blue",
            logging.INFO: "green",
            logging.WARNING: "yellow",
            logging.ERROR: "magenta",
            logging.FATAL: "brred",
        }

    def get_callee_info(self) -> CalleeInfo:
        frame_info: inspect.FrameInfo = inspect.stack()[2]

        module = inspect.getmodule(frame_info.frame)
        module_name = module.__name__ if module else "__main__"

        function_name = frame_info.function
        file = frame_info.filename
        lineno = frame_info.lineno

        return CalleeInfo(
            module_name=module_name,
            fn_name=function_name,
            file=file,
            lineno=lineno,
        )

    def run_loop(self) -> None:
        with open("bot.log", "a+") as f:
            while True:
                log_data = self.queue.get()

                try:
                    if log_data is None:
                        break

                    if isinstance(log_data, LogRecord):
                        level_colour = self.level_colour[log_data.levelno]
                        time = datetime.datetime.now(tz=datetime.UTC)
                        prefix = (
                            f"[{time}] [{level_colour}]{log_data.levelname}[/{level_colour}] "
                            f"[grey]<{log_data.filename}>[/grey] {log_data.name}: "
                        )
                        msg = re.sub(r"^", prefix, escape(log_data.getMessage()), count=0).replace("\n", f"\n{prefix}")
                        self.console.print(msg)
                        f.write(Text.from_markup(msg).plain + "\n")
                        f.flush()
                    else:
                        lg.warning("unexpected log_data type: %s", type(log_data))
                finally:
                    self.queue.task_done()

    def setup_redirect(self) -> None:
        root = logging.getLogger()
        queue_handler = QueueHandler(self.queue)

        for h in root.handlers:
            root.removeHandler(h)

        root.addHandler(queue_handler)

    def shutdown_logger(self) -> None:
        self.queue.put(None)
        self.thread.join()


logger = CustomLogger()
logger.setup_redirect()


# ruff: disable[N802]
def get_custom_logger(*args) -> CustomLogger:
    return logger
