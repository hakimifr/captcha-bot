import uvloop

from captcha_bot.custom_logger import getLogger
from captcha_bot.main import main

if __name__ == "__main__":
    uvloop.run(main())
    getLogger().queue.put(None)
    getLogger().thread.join()
