# SPDX-FileCopyrightText: 2026 Firdaus Hakimi <hakimifirdaus944@gmail.com>
# SPDX-License-Identifier: Apache-2.0

import uvloop

from captcha_bot.custom_logger import get_custom_logger
from captcha_bot.main import main

if __name__ == "__main__":
    uvloop.run(main())
    get_custom_logger().shutdown_logger()
