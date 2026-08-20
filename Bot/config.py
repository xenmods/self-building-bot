import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # --- Telegram Credentials ---
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    API_ID = int(os.getenv("API_ID", "6"))
    API_HASH = os.getenv("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
    
    # --- Owner Configuration ---
    # Can be a single ID or comma-separated IDs (e.g., "12345678,87654321")
    _raw_owners = os.getenv("OWNER_ID", "0")
    OWNER_IDS = [int(x.strip()) for x in _raw_owners.replace(" ", "").split(",") if x.strip().isdigit()]
    if not OWNER_IDS:
        OWNER_IDS = [0]
    OWNER_ID = OWNER_IDS[0]

    # --- AI Brain Configuration ---
    AI_API_BASE = os.getenv("AI_API_BASE", "http://127.0.0.1:8317/v1")
    AI_API_KEY = os.getenv("AI_API_KEY", "dummy")
    AI_MODEL = os.getenv("AI_MODEL", "gpt-4o")
    TRIGGER_WORD = os.getenv("TRIGGER_WORD", "jarvis").strip().lower()
    
    # --- ElevenLabs Configuration ---
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "sk_e0809684ff94c259c894babe7c81424002967675f2f0275f")
    ELEVENLABS_DEFAULT_VOICE = os.getenv("ELEVENLABS_DEFAULT_VOICE", "JBFqnCBsd6RMkjVDRZzb") # George
    ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
    
    # Dynamic bot username (auto-populated on startup)
    BOT_USERNAME = os.getenv("BOT_USERNAME", "").replace("@", "").lower()

    # --- Database Configuration ---
    DB_URI = os.getenv("DB_URI", "sqlite+aiosqlite:///Bot.db")
    MONGO_URI = os.getenv("MONGO_URI", os.getenv("MONGO_URL", ""))
    DB_NAME = os.getenv("DB_NAME", "sample")

    # --- Project Paths ---
    WORKSPACE_ROOT = Path(__file__).parent.parent.resolve()
