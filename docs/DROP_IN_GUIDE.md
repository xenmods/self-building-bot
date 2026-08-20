# 🧠 Drop-In J.A.R.V.I.S. Brain Guide
### *Turn Any Existing Telegram Bot into an Autonomous, Self-Healing, Self-Building Agent*

Have an existing Telegram bot that is unmaintained, has broken commands, or requires tedious manual code edits every time you want a new feature?

You can **drop the J.A.R.V.I.S. Brain into your existing Pyrogram / Kurigram bot in 3 minutes**. Once added, your bot comes alive: you can chat with it in Telegram to debug its own codebase, write new modules, build database models, and restart itself with new capabilities on-the-fly!

---

## ⚡ How It Works

When you install the Brain into an existing bot repository:
1. **Self-Aware Workspace**: The Brain automatically detects the root of your project.
2. **28 Autonomous Tools**: It can read existing files, search code, write new modules in your `modules/` folder, create database models, run pip installs, test Python AST syntax, search web documentation, and visually verify images.
3. **Owner-Secured**: Only user IDs defined in `OWNER_IDS` can command the bot to alter files or run commands.
4. **Persistent Memory**: The bot retains chat history and project facts in SQL across reboots.

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Existing Bot                        │
│                                                             │
│   ├── modules/                                              │
│   │   ├── start.py                                          │
│   │   ├── music.py (broken?)                                │
│   │   └── brain.py  ◄─── [DROP IN] (Autonomous AI Agent)    │
│   ├── sql/                                                  │
│   │   └── brain.py  ◄─── [DROP IN] (SQL History & Memory)   │
│   └── config.py                                             │
└─────────────────────────────────────────────────────────────┘
                               ▲
                               │ "Hey Jarvis, fix the music module
                               │  and add an inline search button!"
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Brain reads music.py and identifies the bug              │
│ 2. Brain replaces the broken code & checks syntax           │
│ 3. Brain executes restart_bot                               │
│ 4. Your bot is fixed and online without touching a terminal!│
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 3-Minute Drop-In Setup

### Step 1: Install Required Dependencies
Add the Brain's required dependencies to your virtual environment or `requirements.txt`:

```bash
pip install httpx openai beautifulsoup4 psutil pillow sqlalchemy aiosqlite
```

### Step 2: Copy the 2 Core Brain Files
Copy the following two files from this repository into your bot's folder structure:

1. [`Bot/modules/brain.py`](../Bot/modules/brain.py) ➔ `<your_project>/Bot/modules/brain.py`
2. [`Bot/sql/brain.py`](../Bot/sql/brain.py) ➔ `<your_project>/Bot/sql/brain.py`

*(If your bot uses a different package name than `Bot`, adjust the import statements at the top of `brain.py` to match your package name).*

### Step 3: Add AI Configuration to your `.env`
Add these environment variables to your `.env` or configuration file:

```env
# AI Agent Configuration (OpenAI Compatible)
AI_API_BASE=https://api.openai.com/v1 # or OpenRouter, Gemini Gateway, Ollama, vLLM, etc.
AI_API_KEY=your_ai_api_key_here
AI_MODEL=gemini-3.7-flash-high        # or gpt-4o, claude-3-5-sonnet, etc.
TRIGGER_WORD=jarvis                   # Wake word for the agent
OWNER_ID=123456789                    # Your Telegram user ID (Required for security)
```

Ensure your `config.py` loads these variables:
```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    OWNER_IDS = [int(x) for x in os.getenv("OWNER_ID", "").split() if x.isdigit()]
    
    # AI Brain Config
    AI_API_BASE = os.getenv("AI_API_BASE", "https://api.openai.com/v1")
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    AI_MODEL = os.getenv("AI_MODEL", "gpt-4o")
    TRIGGER_WORD = os.getenv("TRIGGER_WORD", "jarvis").lower()
    BOT_USERNAME = ""  # Populated dynamically on startup
```

### Step 4: Ensure Database Table Initialization
In your `__main__.py` (or bot startup function), make sure SQLAlchemy models are initialized before `bot.start()`:

```python
from Bot.sql import initialize_database

async def main():
    await initialize_database()  # Creates BrainMessage & BrainMemory tables
    await bot.start()
    ...
```

---

## 💬 What You Can Do Once Dropped In

Once the Brain is loaded, message your bot on Telegram:

### 1. Fix Broken Existing Code
> *"Hey Jarvis, users are reporting an error when running `/play`. Inspect `Bot/modules/music.py`, find the bug, fix it, and reload."*

### 2. Modernize Old Syntax
> *"Jarvis, scan all files in `Bot/modules/` and check for outdated Pyrogram v1 filter syntax like `filters.supergroup` and replace with modern `filters.group`."*

### 3. Add Brand New Capabilities
> *"Hey Jarvis, build a complete level/XP ranking system for group chats with SQLite persistence, command `/rank`, and restart when ready."*

### 4. Self-Diagnose Health
> *"Jarvis, give me full system diagnostics including RAM, CPU, uptime, and loaded modules."*

---

## 🛡️ Security & Sandboxing

- **Owner Authorization**: File edits, shell command execution, and restarts are strictly guarded by `Config.OWNER_IDS`.
- **Pre-Flight Syntax Validation**: J.A.R.V.I.S. automatically runs AST syntax and filter validation before committing any changes to disk.
- **Automatic Backups**: Every modified file is automatically backed up with a timestamp in `.brain_backups/` so you can call `rollback_file` at any time if needed.
