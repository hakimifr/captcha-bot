import asyncio
import logging
import os
import random
import time
from datetime import datetime, timedelta

from pyrogram.client import Client
from pyrogram.enums import ChatMemberStatus, MessageServiceType
from pyrogram.sync import idle
from pyrogram.types.messages_and_media import Message

from captcha_bot import CHAT_WHITELIST, MAX_FAIL_BEFORE_TEMPBAN, TEMP_BAN_SECONDS, TIMEOUT_SECONDS
from captcha_bot.db_util import (
    UserRecord,
    delete_user_record,
    get_user_record,
    increment_consecutive_failures,
    reset_consecutive_failures,
    save_user_record,
)

API_ID = os.getenv("API_ID", "")
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

logger = logging.getLogger(__name__)


async def kicker(app: Client, after: float | int, chat_id: int, user_id: int) -> None:
    await asyncio.sleep(after)

    user_record = get_user_record(chat_id, user_id)
    if user_record is None:
        logger.info(
            "skipping kicker for user %d in chat %d because captcha record no longer exists",
            user_id,
            chat_id,
        )
        return

    captcha_message_id = user_record.challenge_message_id

    try:
        member = await app.get_chat_member(chat_id, user_id)
        failures = increment_consecutive_failures(chat_id, user_id)
        logger.info(
            "Captcha timeout for user %d in chat %d; consecutive failures=%d",
            user_id,
            chat_id,
            failures,
        )

        if failures >= MAX_FAIL_BEFORE_TEMPBAN:
            until_date = datetime.now() + timedelta(seconds=TEMP_BAN_SECONDS)
            await app.ban_chat_member(
                chat_id,
                user_id,
                until_date=until_date,
            )
            await app.send_message(
                chat_id,
                (
                    f"__temporarily banned "
                    f"[{member.user.full_name}](tg://user?id={user_id}) "
                    f"for 6 hours after {MAX_FAIL_BEFORE_TEMPBAN} consecutive failed verifications.__"
                ),
            )
            logger.info(
                "user %d failed captcha for MAX_FAIL_BEFORE_TEMPBAN (%d) times",
                user_id,
                MAX_FAIL_BEFORE_TEMPBAN,
            )
            logger.info(
                "applied 6-hour temp ban to user %d in chat %d until %s after timeout",
                user_id,
                chat_id,
                until_date,
            )
            reset_consecutive_failures(chat_id, user_id)
        else:
            await app.ban_chat_member(chat_id, user_id)
            asyncio.sleep(0.2)
            await app.unban_chat_member(chat_id, user_id)

            await app.send_message(
                chat_id,
                (
                    f"__kicked "
                    f"[{member.user.full_name}](tg://user?id={user_id}) "
                    f"for failing to complete the captcha in time.__"
                ),
            )
            logger.info(
                "Kicked user %d from chat %d due to captcha timeout (consecutive failures=%d)",
                user_id,
                chat_id,
                failures,
            )

            await app.delete_messages(chat_id, int(captcha_message_id))
    except Exception:
        logger.exception(
            "Failed to kick user %d from chat %d",
            user_id,
            chat_id,
        )
    finally:
        delete_user_record(chat_id, user_id)
        await app.delete_messages(chat_id, int(captcha_message_id))


async def joinhandler(app: Client, message: Message) -> None:
    if message.service != MessageServiceType.NEW_CHAT_MEMBERS:
        return

    if not message.chat or not message.new_chat_members:
        return

    assert message.chat.id
    chat_id = message.chat.id

    if chat_id not in CHAT_WHITELIST:
        return

    logger.info(
        "processing new chat members event in chat %d with %d members",
        chat_id,
        len(message.new_chat_members),
    )

    me = await app.get_chat_member(chat_id, "me")
    if me.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
        logger.warning("bot is not admin in chat %d", chat_id)
        return

    for user in message.new_chat_members:
        if user.is_bot:
            logger.info(
                "skipping captcha for bot %d in chat %d",
                user.id,
                chat_id,
            )
            continue

        user_record = get_user_record(chat_id, user.id)
        if user_record and user_record.expires_at - time.time() > 0:
            logger.info("will not re-trigger captcha since user's captcha duration is still valid")
            continue

        expected = random.randint(100000, 999999)  # noqa: S311

        challenge = await app.send_message(
            chat_id,
            (
                f"Welcome, "
                f"[{user.full_name}](tg://user?id={user.id})!\n\n"
                f"Please **reply** to this message with:\n\n"
                f"{expected}\n\n"
                f"Your message **WILL BE IGNORED** if you do not **reply** to this message. "
                f"You have {TIMEOUT_SECONDS} seconds before you're kicked."
            ),
        )
        logger.info(
            "issued captcha challenge for user %d in chat %d (challenge_message_id=%d)",
            user.id,
            chat_id,
            challenge.id,
        )

        expires_at = time.time() + TIMEOUT_SECONDS

        save_user_record(
            chat_id,
            user.id,
            UserRecord(
                expected=expected,
                challenge_message_id=challenge.id,
                expires_at=expires_at,
            ),
        )

        asyncio.create_task(
            kicker(
                app,
                TIMEOUT_SECONDS,
                chat_id,
                user.id,
            )
        )
        logger.info(
            "started kicker timer for user %d in chat %d with timeout=%d",
            user.id,
            chat_id,
            TIMEOUT_SECONDS,
        )


async def verifyhandler(app: Client, message: Message) -> None:
    if not message.chat or not message.from_user or not message.text:
        return

    assert message.chat.id
    chat_id = message.chat.id
    user_id = message.from_user.id

    record = get_user_record(chat_id, user_id)
    if record is None:
        return

    logger.info("received verification message from user %d in chat %d", user_id, chat_id)

    if not message.reply_to_message:
        logger.info(
            "ignoring verification message from user %d in chat %d because it is not a reply",
            user_id,
            chat_id,
        )
        return

    if message.reply_to_message.id != record.challenge_message_id:
        logger.info(
            "ignoring verification message from user %d in chat %d because reply message id %d does not match challenge id %d",  # noqa: E501
            user_id,
            chat_id,
            message.reply_to_message.id,
            record.challenge_message_id,
        )
        return

    if message.text.strip() != str(record.expected):
        await message.reply("__wrong code.__")
        logger.info(
            "user %d submitted wrong captcha in chat %d; retries allowed and consecutive failures unchanged",
            user_id,
            chat_id,
        )
        return

    await message.reply("__Verification successful. Welcome!__")
    await message.reply_to_message.delete()
    logger.info("User %d solved captcha in chat %d", user_id, chat_id)

    reset_consecutive_failures(chat_id, user_id)
    delete_user_record(chat_id, user_id)

    logger.info(
        "User %d successfully completed captcha in chat %d",
        user_id,
        chat_id,
    )


async def main():
    app = Client(
        name="Captcha Bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
    )
    try:
        await app.start()
        await idle()
    finally:
        await app.stop()
