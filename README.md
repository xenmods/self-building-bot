# ⚡ Self-Building Telegram Bot (J.A.R.V.I.S. Core)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Framework Kurigram](https://img.shields.io/badge/Framework-Kurigram%20%2F%20Pyrogram-blueviolet.svg)](https://github.com/kurigram/kurigram)
[![Database SQLAlchemy](https://img.shields.io/badge/Database-SQLAlchemy%20%2B%20SQLite%2FPostgreSQL-green.svg)](https://www.sqlalchemy.org/)
[![AI Engine OpenAI Compatible](https://img.shields.io/badge/AI%20Engine-OpenAI%20%2F%20Gemini%20%2F%20Claude-orange.svg)](https://platform.openai.com/)
[![License MIT](https://img.shields.io/badge/License-MIT-brightgreen.svg)](LICENSE)

An autonomous, self-building, and self-evolving Telegram bot framework powered by modern Large Language Models (OpenAI-compatible APIs, Google Gemini, Claude, or local LLMs). 

Equipped with the **J.A.R.V.I.S. Brain Module**, the bot can autonomously write its own code, create SQL database models, test syntax, search the web for documentation, process & inspect images with computer vision, and reboot itself in real-time to activate new features requested directly through Telegram!

---

## 🌟 Key Features

### 🤖 1. Autonomous Self-Building Agent (`brain.py`)
- **Natural Language Engineering**: Tell the bot *"Hey Jarvis, build a trivia quiz game with score tracking in SQL"* or *"Jarvis, add an AFK system with media support"*, and the agent will plan the architecture, create database models, write the command handlers, validate syntax, and restart itself seamlessly.
- **Smart Access & Security**: Only authorized user IDs defined in `OWNER_IDS` can trigger code modifications or system commands. Non-owners receive a polite refusal.
- **Dynamic Wake Words & Mentions**: Responds to `"jarvis"`, `"hey jarvis"`, commands (`/jarvis`, `/brain`, `/build`, `/code`), bot username mentions (`@YourBot`), replies to bot messages, and 1-on-1 private DMs.

### 🧠 2. Persistent SQL Memory & Fact Retention
- **Survives Reboots**: All conversational turns (`user` and `assistant`) are stored in the database (`BrainMessage` table). Hot-reloads and process reboots never wipe chat memory.
- **Long-Term Episodic Knowledge**: Stores user facts, project codenames, and preferences via the `remember_fact` tool (`BrainMemory` table).
- **Clean Slate**: Easily wipe conversation memory at any time using `/clear`, `/reset`, or `/forget`.

### 👁️ 3. Multimodal Vision & Visual Self-Verification
- **Image Input**: Send photos, stickers, or image documents with questions or prompts (e.g. *"What does this diagram show?"* or *"Recreate this UI in Python"*). The bot downloads and encodes images into base64 Data URLs for multimodal vision models.
- **Autonomous Visual Self-Verification (`vision_analyze_image`)**: When the agent generates a chart, graphic, or image via script, it can visually inspect the output itself to check for visual flaws or alignment errors before sending it to you with `send_telegram_photo`.

### 🛠️ 4. 28 Autonomous Built-in Agent Tools
| Category | Tools | Description |
|---|---|---|
| **Memory & Facts** | `remember_fact`, `recall_facts`, `forget_fact`, `clear_conversation_history` | Persistent episodic knowledge & history management in SQL. |
| **Model Management** | `list_available_models`, `switch_model` | Queries `/v1/models` and switches active LLM models on-the-fly. |
| **Code & Files** | `list_files`, `read_file`, `write_file`, `replace_in_file`, `delete_file`, `search_code` | Explores project files, writes new modules in `Bot/modules/`, updates database models, and searches the codebase. |
| **Safety & Validation**| `check_syntax`, `rollback_file` | Automatic Python AST syntax & framework filter validation before writing, plus automatic timestamped backups in `.brain_backups/`. |
| **Shell & Execution** | `run_command` | Executes terminal commands (`pip install`, `pytest`, scripts) in the virtual environment. |
| **Web Research** | `search_web`, `fetch_web_page` | DuckDuckGo search and clean webpage text scraper for library docs. |
| **Database** | `initialize_database` | Dynamically registers and creates all newly defined SQLAlchemy tables. |
| **Vision & Media** | `vision_analyze_image`, `send_telegram_photo`, `inspect_local_image` | Multimodal visual inspection and sending image files to chats. |
| **Telegram Actions** | `pin_telegram_message`, `unpin_telegram_message`, `send_telegram_message`, `delete_telegram_message`, `get_chat_info` | Telegram chat moderation and messaging tools. |
| **System Diagnostics**| `restart_bot`, `get_system_status` | System health diagnostics (CPU, RAM, uptime, modules) and process reload. |

### 🔄 5. Dynamic Model Discovery & Matrix (`/model`)
- Queries the OpenAI-compatible `/v1/models` endpoint automatically.
- Displays an interactive, paginated inline keyboard with active model checkmarks (`✅`).
- Allows switching models instantly via buttons or `/model <model_name>`.

### 🛑 6. Unbounded Execution, Queueing & `/cancel`
- **No Step Limits**: The agent runs continuously until the task is complete.
- **Task Queueing**: Sending a new request while J.A.R.V.I.S. is busy automatically places it in a FIFO queue and notifies you.
- **Instant Abort (`/cancel`)**: Send `/cancel`, `/stop`, or `/abort` to halt all active subroutines immediately and clear the queue.

### 🛡️ 7. Crash-Proof Isolated Module Loading
- Dynamic module loading in `Bot/modules/__init__.py` isolates each module in a `try...except` sandbox.
- If a generated module has an error, it is logged and isolated—**the bot and J.A.R.V.I.S. Brain remain 100% online**.

---

## 📁 Project Structure

```text
self-building-bot/
├── Bot/
│   ├── core/                   # Framework utilities & decorators
│   │   ├── decorators/         # @handle_errors, @track_user, @rate_limit
│   │   └── utils/              # Formatting and parsing helpers
│   ├── modules/                # Auto-loaded command & feature modules
│   │   ├── __init__.py         # Crash-proof dynamic module loader
│   │   ├── brain.py            # Flagship J.A.R.V.I.S. Autonomous AI Agent
│   │   └── start.py            # /start and /help command handlers
│   ├── sql/                    # SQLAlchemy database models & engines
│   │   ├── __init__.py         # Dynamic model loader & BASE declaration
│   │   ├── brain.py            # Persistent message history & facts models
│   │   └── users.py            # User tracking model
│   ├── config.py               # Centralized configuration & environment loader
│   ├── __init__.py             # Pyrogram client & httpx initialization
│   └── __main__.py             # Entrypoint with lock-retry & table init
├── tests/
│   └── test_brain.py           # Comprehensive unit & integration test suite
├── .env.sample                 # Environment configuration template
├── manage.py                   # CLI runner with supervisor & 'q' to quit
├── requirements.txt            # Project dependencies
└── README.md                   # Project documentation
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10 or higher
- Telegram API Credentials from [my.telegram.org](https://my.telegram.org)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- An OpenAI-compatible API endpoint (OpenAI, Gemini via proxy/gateway, Claude, LocalAI, vLLM, Ollama, etc.)

### 2. Clone and Setup Virtual Environment

```bash
git clone https://github.com/xenmods/self-building-bot.git
cd self-building-bot

# Create and activate virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate

# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy `.env.sample` to `.env` and fill in your credentials:

```bash
cp .env.sample .env
```

Edit `.env`:
```env
# Telegram Bot Configuration
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
API_ID=1234567
API_HASH=abcdef0123456789abcdef0123456789
OWNER_ID=1189238402

# Dual Database URIs
DB_URI=sqlite+aiosqlite:///bot.db
MONGO_URI=

# AI Agent Configuration (OpenAI Compatible)
AI_API_BASE=http://127.0.0.1:8317/v1
AI_API_KEY=dummy
AI_MODEL=gemini-3.7-flash-high
TRIGGER_WORD=jarvis
```

---

## 🎮 Running the Bot

Use the interactive CLI manager:

### Standard Run:
```bash
python manage.py run
```

### Hot-Reloading Development Mode:
Watches the `Bot/` directory and reloads automatically upon file changes:
```bash
python manage.py run --reload
```

### Interactive CLI Controls:
- Press **`q` + Enter** (or type `quit` / `exit`) at any time to cleanly stop the bot.
- Press **`r` + Enter** to manually trigger a reload.
- Press **`Ctrl + C`** for safe shutdown without leaving orphaned session locks.

---

## 💬 Interacting with J.A.R.V.I.S.

Once the bot is online, you can message it directly or in groups:

### Example Prompts:
- **Build a Game**:
  > *"Hey Jarvis, build a complete Connect-4 game where 2 players can play with inline keyboard buttons, track wins/losses in SQL, and restart the bot."*
- **Create an AFK System**:
  > *"Hey Jarvis, build an AFK system where users can type `/afk <text>` or reply to media, and when someone mentions them, reply with their status. Make it persistent in SQL."*
- **Web Research & Vision Infographics**:
  > *"Hey Jarvis, search the web for the latest Python 3.13 features, write a script to generate a summary card image, visually verify the image layout with your vision tool, and send it here."*
- **Persistent Memory**:
  > *"Hey Jarvis, remember that our project release date is next Friday. What features do we currently have loaded?"*

### Built-in Commands:
- `/model` or `/models` — View and switch active AI models with interactive buttons.
- `/clear` or `/reset` — Purge conversation history from SQL database and memory.
- `/cancel` or `/stop` — Abort the currently running task.
- `/start` — Basic welcome and bot introduction.

---

## 🧪 Running the Test Suite

Run the automated test suite to verify tool execution, AST syntax checking, SQL persistence, model switching, and agent simulation:

```bash
python tests/test_brain.py
```

Expected output:
```text
=== Running J.A.R.V.I.S. Test Suite ===
[OK] SQLAlchemy database initialized with Brain models.
[OK] 28 tools verified.
[OK] AST Syntax Validation operational.
[OK] Multiline prompt triggering verified.
[OK] Persistent SQL Message History verified across sessions.
[OK] Persistent Long-term Facts verified in SQL.
[OK] Dynamic Model Keyboard built successfully.
[OK] Model Switching Tool operational.
[OK] File tools operational.
[OK] Agent loop verified.
=== All Tests Succeeded! ===
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
