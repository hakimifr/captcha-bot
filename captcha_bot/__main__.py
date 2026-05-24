import uvloop

from captcha_bot.custom_logger import get_custom_logger
from captcha_bot.main import main

if __name__ == "__main__":
    uvloop.run(main())
    get_custom_logger().shutdown_logger()
