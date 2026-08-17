from pyrogram import Client
from httpx import AsyncClient
import logging
import platform
import subprocess
import sys
from Bot.config import Config

# Install uvloop only on non-Windows platforms
if platform.system() != "Windows":
    try:
        import uvloop
        uvloop.install()
        LOGGER = logging.getLogger(__name__)
        LOGGER.info("uvloop installed for improved performance")
    except ImportError:
        # Try to install uvloop if not already installed
        LOGGER = logging.getLogger(__name__)
        LOGGER.info("Attempting to install uvloop...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "uvloop"])
            import uvloop
            uvloop.install()
            LOGGER.info("uvloop successfully installed and initialized")
        except Exception as e:
            LOGGER.warning(f"Failed to install uvloop: {e}")
            LOGGER.info("Continuing without uvloop")
else:
    LOGGER = logging.getLogger(__name__)
    LOGGER.info("Running on Windows - uvloop not installed")

bot = Client("bot", Config.API_ID, Config.API_HASH, bot_token=Config.BOT_TOKEN) # bot client
session = AsyncClient(timeout=30) # httpx client for requesting urls

# setting up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("log.txt"), logging.StreamHandler()],
    level=logging.INFO,
)

logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
