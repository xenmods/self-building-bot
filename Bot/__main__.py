import asyncio
import pathlib
import sqlite3
import sys

# Ensure project root is in sys.path when started directly or via os.execv
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pyrogram import idle
from Bot import bot, LOGGER
from Bot.modules import *
from Bot.sql import initialize_database
from Bot.config import Config

loop = asyncio.get_event_loop()

async def main():
    await initialize_database()
    LOGGER.info("Starting Bot...")
    
    # Start Pyrogram client with retry in case previous session lock is releasing
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            await bot.start()
            break
        except (sqlite3.OperationalError, Exception) as e:
            if "database is locked" in str(e) and attempt < max_retries:
                LOGGER.warning(f"Session database locked on attempt {attempt}/{max_retries}. Waiting for previous process lock to release...")
                await asyncio.sleep(1.5)
            else:
                raise
    
    # Dynamically fetch bot's username and identity
    try:
        me = await bot.get_me()
        if me:
            if me.username:
                Config.BOT_USERNAME = me.username.lower()
            LOGGER.info(f"Bot Started as @{Config.BOT_USERNAME or me.first_name} (ID: {me.id})")
    except Exception as e:
        LOGGER.warning(f"Could not retrieve bot info on startup: {e}")

    LOGGER.info(f"J.A.R.V.I.S. Brain is online. Trigger word: '{Config.TRIGGER_WORD}' | Owners: {Config.OWNER_IDS}")
    await idle()
    
    try:
        await bot.stop()
    except Exception:
        pass

if __name__ == "__main__":
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        LOGGER.info("--------------------Bot Stopped--------------------")
