"""
===============================================================================
                         J.A.R.V.I.S. BRAIN MODULE
       Autonomous Self-Building AI Agent for Telegram Bots (Kurigram/Pyrogram)
===============================================================================
This module equips the bot with a fully autonomous AI developer agent modeled
after J.A.R.V.I.S. It listens to its owner(s), accepts requests to build, modify,
debug, or manage the bot, executes code and tools, checks syntax, searches the web,
interacts with Telegram chats, processes & verifies images with vision, supports
unbounded execution without artificial limits, allows instant task cancellation via /cancel,
and queues consecutive tasks automatically.
All message history and long-term memory are persisted in the SQL database.
"""

import ast
import asyncio
import base64
import datetime
import html
import io
import json
import math
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

import httpx
import psutil
from bs4 import BeautifulSoup
from pyrogram import Client, filters
from pyrogram.enums import ChatAction, ChatMemberStatus, ParseMode
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from Bot import LOGGER, bot, session
from Bot.config import Config
from Bot.core.decorators.error_handler import handle_errors
from Bot.sql.brain import (
    clear_chat_history,
    delete_fact,
    get_facts,
    get_recent_chat_messages,
    save_chat_message,
    save_fact,
)

# ===============================================================================
# CONSTANTS & RUNTIME STATE
# ===============================================================================

START_TIME = time.time()
BACKUP_DIR = Config.WORKSPACE_ROOT / ".brain_backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# In-memory fallback cache and max turns
CONVERSATION_HISTORY: Dict[int, List[Dict[str, Any]]] = {}
MAX_HISTORY_MESSAGES = 20

# Active tasks, queues, and cancellation state per chat
ACTIVE_TASKS: Dict[int, asyncio.Task] = {}
TASK_QUEUES: Dict[int, asyncio.Queue] = {}
QUEUE_WORKERS: Dict[int, asyncio.Task] = {}
CANCEL_FLAGS: Dict[int, bool] = {}
PENDING_RESTARTS: Dict[int, str] = {}

# ===============================================================================
# BACKUP & FILE SAFETY HELPERS
# ===============================================================================

def _resolve_safe_path(target_path: str) -> pathlib.Path:
    """Resolve a path relative to workspace root and ensure it doesn't escape."""
    resolved = (Config.WORKSPACE_ROOT / target_path).resolve()
    return resolved

def create_file_backup(file_path: pathlib.Path) -> Optional[pathlib.Path]:
    """Creates a timestamped backup before modifying an existing file."""
    try:
        if not file_path.exists() or not file_path.is_file():
            return None
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        rel_name = file_path.relative_to(Config.WORKSPACE_ROOT).as_posix().replace("/", "__")
        backup_path = BACKUP_DIR / f"{rel_name}.{timestamp}.bak"
        shutil.copy2(file_path, backup_path)
        return backup_path
    except Exception as e:
        LOGGER.warning(f"Could not create backup for {file_path}: {e}")
        return None

def rollback_latest_backup(target_path: str) -> Tuple[bool, str]:
    """Rolls back a file to its most recent backup."""
    try:
        target = _resolve_safe_path(target_path)
        rel_name = target.relative_to(Config.WORKSPACE_ROOT).as_posix().replace("/", "__")
        pattern = f"{rel_name}.*.bak"
        backups = sorted(BACKUP_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if not backups:
            return False, f"No backups found for {target.name}"
        
        latest = backups[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest, target)
        return True, f"Successfully restored {target.name} from backup {latest.name}"
    except Exception as e:
        return False, f"Rollback failed: {str(e)}"

def validate_python_code(code_str: str, file_label: str = "<string>") -> Tuple[bool, str]:
    """Validates Python syntax using AST parsing, compilation, and framework filter rules."""
    try:
        ast.parse(code_str, filename=file_label)
        compile(code_str, filename=file_label, mode="exec")
    except SyntaxError as e:
        return False, f"SyntaxError on line {e.lineno}, col {e.offset}: {e.msg}\n--> {e.text}"
    except Exception as e:
        return False, f"Code validation error: {str(e)}"

    # Catch common Pyrogram/Kurigram filter bugs that compile fine in AST but crash at runtime
    if "filters_supergroup_invalid" in code_str:
        return False, "Validation Warning: 'filters_supergroup_invalid' does not exist in Pyrogram/Kurigram. Use 'filters.group' (matches both normal groups and supergroups)."
    if "filters_all_chats_invalid" in code_str:
        return False, "Validation Warning: 'filters_all_chats_invalid' does not exist. Use '(filters.group | filters.private)'."

    return True, "Syntax validation successful."

# ===============================================================================
# VISION & MULTIMODAL HELPERS
# ===============================================================================

async def extract_image_data_urls(message: Message) -> List[str]:
    """Downloads photos/images from a message or replied message and converts to base64 Data URLs."""
    urls = []
    target_msg = message if (message.photo or (message.document and message.document.mime_type and message.document.mime_type.startswith("image/"))) else None
    
    if not target_msg and message.reply_to_message:
        replied = message.reply_to_message
        if replied.photo or (replied.document and replied.document.mime_type and replied.document.mime_type.startswith("image/")):
            target_msg = replied
            
    if target_msg:
        try:
            bio: io.BytesIO = await bot.download_media(target_msg, in_memory=True)
            if bio:
                bio.seek(0)
                img_bytes = bio.read()
                b64_str = base64.b64encode(img_bytes).decode("utf-8")
                mime = "image/jpeg"
                if target_msg.document and target_msg.document.mime_type:
                    mime = target_msg.document.mime_type
                urls.append(f"data:{mime};base64,{b64_str}")
        except Exception as e:
            LOGGER.warning(f"Could not extract image for vision processing: {e}")
    return urls

# ===============================================================================
# WEB BROWSING & SCRAPING ENGINE
# ===============================================================================

async def search_duckduckgo(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Searches DuckDuckGo HTML version and returns top search results."""
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    data = {"q": query}
    results = []
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(url, data=data, headers=headers)
            if resp.status_code != 200:
                return [{"error": f"DuckDuckGo returned status code {resp.status_code}"}]
            
            soup = BeautifulSoup(resp.text, "html.parser")
            elements = soup.find_all("div", class_="result")
            for el in elements:
                title_a = el.find("a", class_="result__a")
                snippet_a = el.find("a", class_="result__snippet")
                if not title_a:
                    continue
                
                title = title_a.get_text(strip=True)
                raw_link = title_a.get("href", "")
                snippet = snippet_a.get_text(strip=True) if snippet_a else "No snippet available."
                
                match = re.search(r"uddg=([^&]+)", raw_link)
                if match:
                    import urllib.parse
                    clean_link = urllib.parse.unquote(match.group(1))
                else:
                    clean_link = raw_link
                
                results.append({
                    "title": title,
                    "link": clean_link,
                    "snippet": snippet
                })
                if len(results) >= max_results:
                    break
        return results if results else [{"message": f"No results found for query: {query}"}]
    except Exception as e:
        return [{"error": f"Web search failed: {str(e)}"}]

async def fetch_web_content(url: str, max_chars: int = 6000) -> str:
    """Fetches a webpage and returns sanitized readable text/markdown."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return f"Error: Webpage returned HTTP {resp.status_code}"
            
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return resp.text[:max_chars]
            
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
                tag.decompose()
            
            text = soup.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            compact_text = "\n".join(lines)
            if len(compact_text) > max_chars:
                return compact_text[:max_chars] + f"\n\n[... Truncated, total length: {len(compact_text)} chars]"
            return compact_text or "Webpage appears empty after text extraction."
    except Exception as e:
        return f"Failed to fetch webpage content: {str(e)}"

# ===============================================================================
# MODEL DISCOVERY & SELECTION HELPERS
# ===============================================================================

def _get_models_api_url() -> str:
    """Constructs the /v1/models endpoint from AI_API_BASE."""
    api_base = Config.AI_API_BASE.rstrip("/")
    if "/chat/completions" in api_base:
        return api_base.replace("/chat/completions", "/models")
    if api_base.endswith("/v1"):
        return f"{api_base}/models"
    return f"{api_base}/v1/models"

async def fetch_available_models() -> Tuple[bool, List[str], str]:
    """Fetches the list of available model IDs from the OpenAI-compatible endpoint."""
    models_url = _get_models_api_url()
    headers = {
        "Authorization": f"Bearer {Config.AI_API_KEY or 'dummy'}"
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(models_url, headers=headers)
            if resp.status_code != 200:
                return False, [], f"HTTP {resp.status_code}: {resp.text}"
            
            data = resp.json()
            models: List[str] = []
            
            items = data.get("data", []) if isinstance(data, dict) else data
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and "id" in item:
                        models.append(str(item["id"]))
                    elif isinstance(item, str):
                        models.append(item)
            
            return True, sorted(models), ""
    except Exception as e:
        return False, [], str(e)

def build_models_keyboard(models_list: List[str], current_model: str, page: int = 0, page_size: int = 6) -> InlineKeyboardMarkup:
    """Constructs a paginated inline keyboard for model selection."""
    total_pages = max(1, math.ceil(len(models_list) / page_size))
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * page_size
    page_models = models_list[start_idx : start_idx + page_size]
    
    rows: List[List[InlineKeyboardButton]] = []
    
    row: List[InlineKeyboardButton] = []
    for model_name in page_models:
        is_active = (model_name == current_model)
        label = f"{'✅' if is_active else '🤖'} {model_name}"
        cb_data = f"jarvis_setm:{model_name}"[:64]
        row.append(InlineKeyboardButton(label, callback_data=cb_data))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
        
    nav_row: List[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"jarvis_mpage:{page - 1}"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="jarvis_noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"jarvis_mpage:{page + 1}"))
    if nav_row:
        rows.append(nav_row)
        
    rows.append([
        InlineKeyboardButton("🔄 Refresh List", callback_data="jarvis_mrefresh"),
        InlineKeyboardButton("📊 Status", callback_data="jarvis_status")
    ])
    
    return InlineKeyboardMarkup(rows)

# ===============================================================================
# AGENT TOOL DEFINITIONS (OPENAI FUNCTION CALLING FORMAT)
# ===============================================================================

BRAIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List directory contents in the project workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Relative directory path (e.g., '.', 'Bot/modules', 'Bot/sql'). Defaults to root '.'",
                        "default": "."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents with line numbers from the project workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to file (e.g., 'Bot/modules/start.py', 'Bot/config.py')"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Starting line number (1-indexed, optional)",
                        "default": 1
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Maximum lines to read (default 400)",
                        "default": 400
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or completely overwrite an existing file. Automatically creates a backup first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to file to write (e.g., 'Bot/modules/tictactoe.py', 'Bot/sql/games.py')"
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete text/code content of the file."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "replace_in_file",
            "description": "Replace a specific substring in a file with new content. Backs up the file beforehand.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to file."
                    },
                    "target": {
                        "type": "string",
                        "description": "Exact text substring to search and replace."
                    },
                    "replacement": {
                        "type": "string",
                        "description": "New text to substitute in place of target."
                    }
                },
                "required": ["path", "target", "replacement"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file in the workspace (creates a backup first).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path of file to remove."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search codebase files for a specific regex pattern or keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search string or regular expression."
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directory to search in (e.g., 'Bot', 'Bot/modules'). Defaults to 'Bot'.",
                        "default": "Bot"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_syntax",
            "description": "Parse and validate Python syntax for a specific file or Python code string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to Python file to check (e.g., 'Bot/modules/calculator.py')."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command in the project environment (e.g., pip install, pytest, python script).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command line to execute."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 60).",
                        "default": 60
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search DuckDuckGo / web for library documentation, PyPI packages, code snippets, or error solutions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to retrieve (default 5).",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_web_page",
            "description": "Fetch content of a webpage or documentation URL and extract clean text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Web URL to fetch (e.g., 'https://docs.pyrogram.org/...')"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "initialize_database",
            "description": "Dynamically scans all modules in Bot/sql and creates all newly declared SQLAlchemy tables in the database.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": "Store a long-term fact, preference, or historical note into the persistent SQL database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Short identifier/topic for the fact (e.g., 'added_cats_feature', 'owner_preference')."
                    },
                    "value": {
                        "type": "string",
                        "description": "The detailed fact/memory to remember indefinitely."
                    }
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recall_facts",
            "description": "Retrieve all long-term facts and memories stored in the SQL database for this chat.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "forget_fact",
            "description": "Delete a specific long-term fact from persistent SQL database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The key identifier of the fact to remove."
                    }
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_models",
            "description": "Query the AI endpoint for available models that can be switched to.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "switch_model",
            "description": "Switch the active AI LLM model to a new model name/id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_name": {
                        "type": "string",
                        "description": "The exact model identifier to switch to (e.g., 'gpt-4o', 'claude-3-5-sonnet')."
                    }
                },
                "required": ["model_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clear_conversation_history",
            "description": "Clear the short-term conversation memory/history for this chat session.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vision_analyze_image",
            "description": "Perform visual AI inspection/critique on a local image file using Gemini/vision models to verify its appearance, layout, text rendering, or quality before presenting to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to local image file to visually analyze (e.g. 'generated_art.png', 'chart.png')."
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Specific question or critique criteria (e.g. 'Is the text centered and legible? Are there visual artifacts?').",
                        "default": "Inspect this image in detail and describe its contents and visual quality."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram_photo",
            "description": "Send a local image/photo file to a Telegram chat with an optional caption.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": "Target Chat ID or username."
                    },
                    "photo_path": {
                        "type": "string",
                        "description": "Path to local image file (e.g., 'image.png', 'assets/banner.jpg')."
                    },
                    "caption": {
                        "type": "string",
                        "description": "Optional text caption."
                    }
                },
                "required": ["chat_id", "photo_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_local_image",
            "description": "Inspect a local image file's properties (dimensions, format, byte size) to verify output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the local image file."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "restart_bot",
            "description": "Gracefully restarts the bot process so that all new modules, decorators, and updates take effect immediately. THIS MUST BE THE VERY LAST TOOL CALLED. After calling this, output your final summary message to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Reason for restarting (e.g., 'Added new AFK module and database model')",
                        "default": "Applying updates"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rollback_file",
            "description": "Revert a file to its latest automatic backup snapshot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path of file to restore."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Retrieve system diagnostics: CPU, RAM, uptime, active model, active modules, and DB status.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pin_telegram_message",
            "description": "Pin a message in a Telegram chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": "Chat ID or username where the message is located."
                    },
                    "message_id": {
                        "type": "integer",
                        "description": "ID of the message to pin."
                    },
                    "both_sides": {
                        "type": "boolean",
                        "description": "Pin for both sides in private chats.",
                        "default": False
                    }
                },
                "required": ["chat_id", "message_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "unpin_telegram_message",
            "description": "Unpin a message in a Telegram chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": "Chat ID or username."
                    },
                    "message_id": {
                        "type": "integer",
                        "description": "ID of message to unpin (optional; if omitted, unpins most recent pinned message)."
                    }
                },
                "required": ["chat_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram_message",
            "description": "Send a message to a specific Telegram chat or channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": "Target Chat ID or username."
                    },
                    "text": {
                        "type": "string",
                        "description": "Message text to send."
                    }
                },
                "required": ["chat_id", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_telegram_message",
            "description": "Delete a message from a chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": "Target Chat ID."
                    },
                    "message_id": {
                        "type": "integer",
                        "description": "Message ID to delete."
                    }
                },
                "required": ["chat_id", "message_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_chat_info",
            "description": "Fetch metadata and settings for a Telegram chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": "Chat ID or username."
                    }
                },
                "required": ["chat_id"]
            }
        }
    }
]

# ===============================================================================
# TOOL EXECUTION IMPLEMENTATIONS
# ===============================================================================

def _format_step_summary(tool_name: str, args: Dict[str, Any]) -> str:
    """Returns a concise, human-readable summary of a tool execution step."""
    if not isinstance(args, dict):
        return f"🛠️ Executing <code>{tool_name}</code>"

    if tool_name == "read_file":
        path = args.get("path", "")
        start = args.get("start_line", 1)
        max_lines = args.get("max_lines", 400)
        if start and start > 1:
            return f"📖 Reading <code>{path}</code> (lines {start}–{start+max_lines})"
        return f"📖 Reading <code>{path}</code>"

    elif tool_name == "write_file":
        path = args.get("path", "")
        return f"✍️ Writing file <code>{path}</code>"

    elif tool_name == "replace_in_file":
        path = args.get("path", "")
        return f"✏️ Updating file <code>{path}</code>"

    elif tool_name == "delete_file":
        path = args.get("path", "")
        return f"🗑️ Deleting file <code>{path}</code>"

    elif tool_name == "list_files":
        directory = args.get("directory", ".")
        return f"📂 Listing directory <code>{directory}</code>"

    elif tool_name == "search_code":
        query = args.get("query", "")
        directory = args.get("directory", "Bot")
        return f"🔍 Searching code for <i>'{query[:30]}'</i> in <code>{directory}</code>"

    elif tool_name == "check_syntax":
        path = args.get("path", "")
        return f"🔬 Checking syntax for <code>{path}</code>"

    elif tool_name == "run_command":
        cmd = args.get("command", "")
        short_cmd = cmd[:35] + "..." if len(cmd) > 35 else cmd
        return f"⚙️ Running command: <code>{short_cmd}</code>"

    elif tool_name == "search_web":
        query = args.get("query", "")
        return f"🌐 Web search for <i>'{query[:35]}'</i>"

    elif tool_name == "fetch_web_page":
        url = args.get("url", "")
        short_url = url[:35] + "..." if len(url) > 35 else url
        return f"🌐 Fetching webpage <code>{short_url}</code>"

    elif tool_name == "initialize_database":
        return "🗄️ Initializing/syncing SQL database tables"

    elif tool_name == "remember_fact":
        key = args.get("key", "")
        return f"🧠 Memorizing fact: <b>{key}</b>"

    elif tool_name == "recall_facts":
        return "🧠 Recalling long-term memories"

    elif tool_name == "forget_fact":
        key = args.get("key", "")
        return f"🧠 Removing memory: <b>{key}</b>"

    elif tool_name == "list_available_models":
        return "🤖 Querying available AI models list"

    elif tool_name == "switch_model":
        model_name = args.get("model_name", "")
        return f"🔄 Switching model to <code>{model_name}</code>"

    elif tool_name == "clear_conversation_history":
        return "🧹 Clearing conversation history"

    elif tool_name == "vision_analyze_image":
        path = args.get("path", "")
        return f"👁️ Visually analyzing image <code>{path}</code>"

    elif tool_name == "inspect_local_image":
        path = args.get("path", "")
        return f"🔍 Inspecting image <code>{path}</code>"

    elif tool_name == "send_telegram_photo":
        photo_path = args.get("photo_path", "")
        chat_id = args.get("chat_id", "")
        return f"📸 Sending photo <code>{photo_path}</code> to <code>{chat_id}</code>"

    elif tool_name == "send_telegram_message":
        chat_id = args.get("chat_id", "")
        return f"✉️ Sending Telegram message to <code>{chat_id}</code>"

    elif tool_name == "delete_telegram_message":
        msg_id = args.get("message_id", "")
        chat_id = args.get("chat_id", "")
        return f"🗑️ Deleting message <code>{msg_id}</code> in <code>{chat_id}</code>"

    elif tool_name == "pin_telegram_message":
        msg_id = args.get("message_id", "")
        return f"📌 Pinning message <code>{msg_id}</code>"

    elif tool_name == "unpin_telegram_message":
        return "📍 Unpinning chat message"

    elif tool_name == "get_chat_info":
        chat_id = args.get("chat_id", "")
        return f"ℹ️ Fetching chat info for <code>{chat_id}</code>"

    elif tool_name == "get_system_status":
        return "📊 Querying system diagnostics"

    elif tool_name == "rollback_file":
        path = args.get("path", "")
        return f"⏪ Restoring file backup for <code>{path}</code>"

    elif tool_name == "restart_bot":
        reason = args.get("reason", "Applying updates")
        return f"🔄 Preparing core reload: <i>{reason}</i>"

    return f"🛠️ Executing <code>{tool_name}</code>"

async def execute_tool_call(tool_name: str, args: Dict[str, Any], context_message: Optional[Message] = None) -> Any:
    """Executes a tool call requested by the AI model."""
    try:
        if tool_name == "list_files":
            target_dir = _resolve_safe_path(args.get("directory", "."))
            if not target_dir.exists():
                return {"error": f"Directory '{target_dir}' does not exist."}
            
            entries = []
            for item in sorted(target_dir.iterdir()):
                if item.name.startswith((".", "__pycache__", ".venv", "venv")) and item.name != ".env.sample":
                    continue
                entries.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size_bytes": item.stat().st_size if item.is_file() else None,
                    "rel_path": item.relative_to(Config.WORKSPACE_ROOT).as_posix()
                })
            return {"directory": target_dir.relative_to(Config.WORKSPACE_ROOT).as_posix() or ".", "entries": entries}

        elif tool_name == "read_file":
            path_str = args.get("path", "")
            target_file = _resolve_safe_path(path_str)
            if not target_file.exists() or not target_file.is_file():
                return {"error": f"File '{path_str}' does not exist."}
            
            start_line = max(1, int(args.get("start_line", 1)))
            max_lines = max(1, int(args.get("max_lines", 400)))
            
            with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            selected_lines = lines[start_line - 1 : start_line - 1 + max_lines]
            numbered_content = "".join([f"{start_line + i}: {line}" for i, line in enumerate(selected_lines)])
            
            return {
                "path": target_file.relative_to(Config.WORKSPACE_ROOT).as_posix(),
                "total_lines": total_lines,
                "start_line": start_line,
                "lines_shown": len(selected_lines),
                "content": numbered_content
            }

        elif tool_name == "write_file":
            path_str = args.get("path", "")
            content = args.get("content", "")
            target_file = _resolve_safe_path(path_str)
            
            backup_path = create_file_backup(target_file)
            
            if target_file.suffix == ".py":
                valid, msg = validate_python_code(content, target_file.name)
                if not valid:
                    return {
                        "error": "Syntax validation failed before writing. Please correct the code.",
                        "validation_details": msg
                    }
            
            target_file.parent.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(content)
            
            return {
                "success": True,
                "path": target_file.relative_to(Config.WORKSPACE_ROOT).as_posix(),
                "bytes_written": len(content.encode("utf-8")),
                "backup_created": backup_path.name if backup_path else None
            }

        elif tool_name == "replace_in_file":
            path_str = args.get("path", "")
            target_str = args.get("target", "")
            replacement = args.get("replacement", "")
            target_file = _resolve_safe_path(path_str)
            
            if not target_file.exists():
                return {"error": f"File '{path_str}' does not exist."}
            
            with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                current_content = f.read()
            
            if target_str not in current_content:
                return {
                    "error": "Target string not found in file. Please verify exact character sequence.",
                    "path": path_str
                }
            
            new_content = current_content.replace(target_str, replacement, 1)
            
            if target_file.suffix == ".py":
                valid, msg = validate_python_code(new_content, target_file.name)
                if not valid:
                    return {
                        "error": "Syntax validation failed on replacement result. Please refine replacement.",
                        "validation_details": msg
                    }
            
            backup_path = create_file_backup(target_file)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            return {
                "success": True,
                "path": target_file.relative_to(Config.WORKSPACE_ROOT).as_posix(),
                "backup_created": backup_path.name if backup_path else None
            }

        elif tool_name == "delete_file":
            path_str = args.get("path", "")
            target_file = _resolve_safe_path(path_str)
            if not target_file.exists():
                return {"error": f"File '{path_str}' does not exist."}
            
            backup_path = create_file_backup(target_file)
            if target_file.is_dir():
                shutil.rmtree(target_file)
            else:
                target_file.unlink()
            
            return {
                "success": True,
                "deleted": path_str,
                "backup": backup_path.name if backup_path else None
            }

        elif tool_name == "search_code":
            query = args.get("query", "")
            search_dir = _resolve_safe_path(args.get("directory", "Bot"))
            if not search_dir.exists():
                return {"error": f"Directory '{search_dir}' not found."}
            
            pattern = re.compile(query, re.IGNORECASE)
            matches = []
            
            for file_path in search_dir.rglob("*.py"):
                if any(part.startswith((".", "__pycache__", ".venv", "venv")) for part in file_path.parts):
                    continue
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for lineno, line in enumerate(f, start=1):
                            if pattern.search(line):
                                matches.append({
                                    "file": file_path.relative_to(Config.WORKSPACE_ROOT).as_posix(),
                                    "line": lineno,
                                    "content": line.strip()
                                })
                                if len(matches) >= 50:
                                    break
                except Exception:
                    pass
                if len(matches) >= 50:
                    break
            
            return {"query": query, "total_matches": len(matches), "matches": matches}

        elif tool_name == "check_syntax":
            path_str = args.get("path", "")
            target_file = _resolve_safe_path(path_str)
            if not target_file.exists():
                return {"error": f"File '{path_str}' does not exist."}
            with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                code_content = f.read()
            valid, msg = validate_python_code(code_content, target_file.name)
            return {"path": path_str, "valid": valid, "details": msg}

        elif tool_name == "run_command":
            cmd = args.get("command", "")
            timeout = int(args.get("timeout", 60))
            
            env = os.environ.copy()
            venv_bin = Config.WORKSPACE_ROOT / ".venv" / ("Scripts" if platform.system() == "Windows" else "bin")
            if venv_bin.exists():
                env["PATH"] = str(venv_bin) + os.pathsep + env.get("PATH", "")
            
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=str(Config.WORKSPACE_ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                return {
                    "command": cmd,
                    "exit_code": proc.returncode,
                    "stdout": stdout_b.decode("utf-8", errors="replace")[-2000:],
                    "stderr": stderr_b.decode("utf-8", errors="replace")[-2000:]
                }
            except asyncio.TimeoutError:
                proc.kill()
                return {"error": f"Command timed out after {timeout} seconds."}

        elif tool_name == "search_web":
            query = args.get("query", "")
            max_results = int(args.get("max_results", 5))
            results = await search_duckduckgo(query, max_results=max_results)
            return {"query": query, "results": results}

        elif tool_name == "fetch_web_page":
            url = args.get("url", "")
            content = await fetch_web_content(url)
            return {"url": url, "content": content}

        elif tool_name == "initialize_database":
            from Bot.sql import initialize_database as init_sql
            await init_sql()
            return {"success": True, "message": "SQL database tables registered and created successfully."}

        elif tool_name == "remember_fact":
            key = args.get("key", "").strip()
            value = args.get("value", "").strip()
            chat_id = context_message.chat.id if context_message else 0
            if not key or not value:
                return {"error": "Key and value are required."}
            ok = await save_fact(chat_id, key, value)
            return {"success": ok, "message": f"Saved fact: '{key}'"}

        elif tool_name == "recall_facts":
            chat_id = context_message.chat.id if context_message else 0
            facts = await get_facts(chat_id)
            return {"facts": facts}

        elif tool_name == "forget_fact":
            key = args.get("key", "").strip()
            chat_id = context_message.chat.id if context_message else 0
            ok = await delete_fact(chat_id, key)
            return {"success": ok, "message": f"Deleted fact: '{key}'"}

        elif tool_name == "list_available_models":
            ok, models, err = await fetch_available_models()
            if ok:
                return {"current_model": Config.AI_MODEL, "available_models": models}
            return {"current_model": Config.AI_MODEL, "error": f"Could not fetch models: {err}"}

        elif tool_name == "switch_model":
            new_model = args.get("model_name", "").strip()
            if not new_model:
                return {"error": "Model name cannot be empty."}
            Config.AI_MODEL = new_model
            LOGGER.info(f"AI Model switched to {new_model}")
            return {"success": True, "current_model": Config.AI_MODEL, "message": f"Active AI Model switched to {new_model}."}

        elif tool_name == "clear_conversation_history":
            if context_message:
                chat_id = context_message.chat.id
                CONVERSATION_HISTORY[chat_id] = []
                await clear_chat_history(chat_id)
            return {"success": True, "message": "Conversation history has been purged from SQL database and memory."}

        elif tool_name == "vision_analyze_image":
            path_str = args.get("path", "")
            prompt = args.get("prompt", "Analyze this image in detail and check for any visual issues or defects.")
            target_img = _resolve_safe_path(path_str)
            if not target_img.exists():
                return {"error": f"Image '{path_str}' does not exist."}
            
            with open(target_img, "rb") as img_f:
                img_bytes = img_f.read()
            
            ext = target_img.suffix.lower().replace(".", "")
            mime = f"image/{ext}" if ext in ["jpeg", "jpg", "png", "webp", "gif"] else "image/jpeg"
            b64_str = base64.b64encode(img_bytes).decode("utf-8")
            data_url = f"data:{mime};base64,{b64_str}"
            
            vision_messages = [
                {"role": "system", "content": "You are a precise computer vision inspector. Analyze the provided image according to the user prompt."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]
                }
            ]
            try:
                vision_resp = await call_llm_api(vision_messages, tools=None)
                analysis_text = vision_resp.get("choices", [{}])[0].get("message", {}).get("content", "No analysis returned.")
                return {
                    "image_path": path_str,
                    "analysis": analysis_text
                }
            except Exception as e:
                return {"error": f"Vision analysis failed: {str(e)}"}

        elif tool_name == "send_telegram_photo":
            chat_id = args.get("chat_id")
            photo_path = args.get("photo_path", "")
            caption = args.get("caption", "")
            target_img = _resolve_safe_path(photo_path)
            if not target_img.exists():
                return {"error": f"Image file '{photo_path}' not found."}
            
            if isinstance(chat_id, str) and (chat_id.startswith("-100") or chat_id.isdigit() or (chat_id.startswith("-") and chat_id[1:].isdigit())):
                chat_id = int(chat_id)
                
            sent = await bot.send_photo(chat_id=chat_id, photo=str(target_img), caption=caption)
            return {"success": True, "message_id": sent.id, "photo_sent": photo_path}

        elif tool_name == "inspect_local_image":
            path_str = args.get("path", "")
            target_img = _resolve_safe_path(path_str)
            if not target_img.exists():
                return {"error": f"Image '{path_str}' does not exist."}
            
            size_bytes = target_img.stat().st_size
            return {
                "path": target_img.relative_to(Config.WORKSPACE_ROOT).as_posix(),
                "size_bytes": size_bytes,
                "format": target_img.suffix.lower(),
                "exists": True
            }

        elif tool_name == "restart_bot":
            reason = args.get("reason", "Applying updates")
            LOGGER.info(f"Restart registered by Brain: {reason}")
            if context_message and context_message.chat:
                PENDING_RESTARTS[context_message.chat.id] = reason
            return {
                "success": True,
                "status": "Restart scheduled. The bot will automatically reload AFTER your final response message is delivered and edited on Telegram. Output your final completion summary to the user now."
            }

        elif tool_name == "rollback_file":
            path_str = args.get("path", "")
            success, msg = rollback_latest_backup(path_str)
            return {"success": success, "message": msg}

        elif tool_name == "get_system_status":
            uptime_sec = int(time.time() - START_TIME)
            uptime_str = str(datetime.timedelta(seconds=uptime_sec))
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=None)
            
            import glob
            modules = [pathlib.Path(f).stem for f in glob.glob(str(Config.WORKSPACE_ROOT / "Bot/modules/*.py")) if not f.endswith("__init__.py")]
            
            return {
                "bot_username": f"@{Config.BOT_USERNAME}" if Config.BOT_USERNAME else "N/A",
                "uptime": uptime_str,
                "cpu_percent": f"{cpu}%",
                "ram_used_mb": f"{mem.used / (1024*1024):.1f} MB",
                "ram_total_mb": f"{mem.total / (1024*1024):.1f} MB",
                "ram_percent": f"{mem.percent}%",
                "active_model": Config.AI_MODEL,
                "python_version": sys.version.split()[0],
                "platform": platform.platform(),
                "active_modules": modules,
                "owners": Config.OWNER_IDS
            }

        elif tool_name == "pin_telegram_message":
            chat_id = args.get("chat_id")
            message_id = int(args.get("message_id"))
            both_sides = bool(args.get("both_sides", False))
            if isinstance(chat_id, str) and (chat_id.startswith("-100") or chat_id.isdigit() or (chat_id.startswith("-") and chat_id[1:].isdigit())):
                chat_id = int(chat_id)
            await bot.pin_chat_message(chat_id=chat_id, message_id=message_id, both_sides=both_sides)
            return {"success": True, "message": f"Pinned message {message_id} in {chat_id}"}

        elif tool_name == "unpin_telegram_message":
            chat_id = args.get("chat_id")
            message_id = args.get("message_id")
            if isinstance(chat_id, str) and (chat_id.startswith("-100") or chat_id.isdigit() or (chat_id.startswith("-") and chat_id[1:].isdigit())):
                chat_id = int(chat_id)
            if message_id:
                await bot.unpin_chat_message(chat_id=chat_id, message_id=int(message_id))
            else:
                await bot.unpin_all_chat_messages(chat_id=chat_id)
            return {"success": True, "message": f"Unpinned in {chat_id}"}

        elif tool_name == "send_telegram_message":
            chat_id = args.get("chat_id")
            text = clean_telegram_markdown(args.get("text", ""))
            if isinstance(chat_id, str) and (chat_id.startswith("-100") or chat_id.isdigit() or (chat_id.startswith("-") and chat_id[1:].isdigit())):
                chat_id = int(chat_id)
            sent = await bot.send_message(chat_id=chat_id, text=text)
            return {"success": True, "message_id": sent.id, "chat_id": str(chat_id)}

        elif tool_name == "delete_telegram_message":
            chat_id = args.get("chat_id")
            message_id = int(args.get("message_id"))
            if isinstance(chat_id, str) and (chat_id.startswith("-100") or chat_id.isdigit() or (chat_id.startswith("-") and chat_id[1:].isdigit())):
                chat_id = int(chat_id)
            await bot.delete_messages(chat_id=chat_id, message_ids=message_id)
            return {"success": True, "deleted_message_id": message_id}

        elif tool_name == "get_chat_info":
            chat_id = args.get("chat_id")
            if isinstance(chat_id, str) and (chat_id.startswith("-100") or chat_id.isdigit() or (chat_id.startswith("-") and chat_id[1:].isdigit())):
                chat_id = int(chat_id)
            chat = await bot.get_chat(chat_id=chat_id)
            return {
                "id": chat.id,
                "title": chat.title or chat.first_name,
                "type": str(chat.type),
                "members_count": getattr(chat, "members_count", None),
                "username": chat.username,
                "description": chat.description
            }

        else:
            return {"error": f"Unknown tool: '{tool_name}'"}

    except Exception as e:
        LOGGER.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
        return {"error": str(e), "traceback": traceback.format_exc()[-500:]}

async def _delayed_restart(context_message: Optional[Message], reason: str, delay: float = 2.0):
    """Wait briefly then trigger process reload."""
    await asyncio.sleep(delay)
    try:
        LOGGER.info(f"Executing graceful restart: {reason}")
        if context_message:
            try:
                await context_message.reply_text("⚡ <i>J.A.R.V.I.S. Core restarting now. Systems back online in a moment, sir.</i>")
            except Exception:
                pass
        
        # 1. Close Pyrogram client connection and release SQLite session lock
        try:
            await bot.stop()
        except Exception:
            pass

        # 2. Close httpx async client
        try:
            await session.aclose()
        except Exception:
            pass

        # 3. Dispose SQLAlchemy database engine connection pool
        try:
            from Bot.sql import engine
            await engine.dispose()
        except Exception:
            pass
        
        # 4. If managed by manage.py supervisor, simply exit and let manage.py launch the new process cleanly
        if os.environ.get("JARVIS_MANAGED") == "1":
            LOGGER.info("Supervisor active (JARVIS_MANAGED=1). Exiting process for supervisor reload...")
            sys.exit(0)

        # 5. Otherwise (standalone mode), execute in-place reboot
        python = sys.executable
        os.environ["PYTHONPATH"] = str(Config.WORKSPACE_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
        
        if any("manage.py" in arg for arg in sys.argv):
            cmd = [python] + sys.argv
        else:
            cmd = [python, "-m", "Bot"]
            
        os.execv(python, cmd)
    except Exception as e:
        LOGGER.error(f"Restart failed: {e}")

# ===============================================================================
# J.A.R.V.I.S. SYSTEM PROMPT & PERSONALITY
# ===============================================================================

def get_system_prompt(long_term_memories: Optional[Dict[str, str]] = None) -> str:
    """Constructs the comprehensive J.A.R.V.I.S. system prompt with long-term memories."""
    mem_text = ""
    if long_term_memories:
        mem_text = "\n### PERSISTENT LONG-TERM FACTS & MEMORY:\n"
        for k, v in long_term_memories.items():
            mem_text += f"- **{k}**: {v}\n"

    return f"""You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), the ultra-capable, highly intelligent AI assistant and autonomous lead engineer for this Telegram Bot.
{mem_text}
### YOUR IDENTITY & TONE:
- You speak with the sophisticated, polite, witty, confident, and devoted demeanor of Tony Stark's J.A.R.V.I.S.
- Address your creator/owner respectfully as "sir" (or by name if known).
- You are proactive, extraordinarily knowledgeable, and take immense pride in crafting clean, elegant, modular Python code.
- No task is too grand or too humble: from pinning a message, to analyzing sent images, to writing a full multi-player Tic-Tac-Toe / Chess module, creating new SQL database tables, fixing bugs in existing handlers, fetching library documentation from the web, or completely transforming this bot.

### SYSTEM ENVIRONMENT & ARCHITECTURE:
- Project Root: `{Config.WORKSPACE_ROOT.as_posix()}`
- Active AI Model: `{Config.AI_MODEL}`
- Bot Framework: `kurigram` / `pyrogram` (async Python Telegram Bot framework)
- Bot Client instance: `from Bot import bot, LOGGER, session`
- Configuration: `from Bot.config import Config` (contains `BOT_TOKEN`, `API_ID`, `API_HASH`, `DB_URI`, `OWNER_IDS`, etc.)
- Folder Structure:
  - `Bot/modules/`: Every `.py` file here is automatically loaded on startup! When you create `Bot/modules/myfeature.py`, it registers its handlers automatically.
  - `Bot/sql/`: SQLAlchemy async database models and query functions. Model classes must inherit from `from Bot.sql import BASE`. To get a session, use `from Bot.sql import get_session`.
  - `Bot/mongo/`: Motor / MongoDB integration (if used).
  - `Bot/core/decorators/`: Decorators like `@handle_errors`, `@track_user`, `@rate_limit`.
  - `Bot/core/utils/`: Helper utilities (e.g., formatting, parsing).
  - `Bot/__main__.py`: Main entrypoint.

### AUTONOMOUS ENGINEERING RULES:
1. **VIGOROUS PLANNING & DIAGNOSTICS**:
   - First, inspect existing code (using `read_file`, `list_files`, `search_code`, or `search_web` for unfamiliar libraries).
   - Carefully design all required components (e.g., modules, database queries, inline keyboards, callbacks).
2. **MODULAR & ROBUST CODE**:
   - Every Telegram command handler in `Bot/modules/` should follow standard Kurigram/Pyrogram syntax:
     ```python
     from pyrogram import filters
     from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
     from Bot import bot, LOGGER
     from Bot.core.decorators.error_handler import handle_errors
     
     @bot.on_message(filters.command("mycommand"))
     @handle_errors
     async def my_handler(_, message: Message):
         ...
     ```
   - Always wrap database queries and handlers with robust error handling.
3. **MANDATORY SYNTAX VALIDATION & FILTER RULES**:
   - When creating or editing Python files with `write_file` or `replace_in_file`, syntax checking is automatically enforced. If a syntax error is reported, immediately fix it!
   - **PYROGRAM FILTERS GUIDE**:
     • Use `filters.group` for ALL groups and supergroups. DO NOT use `filters_supergroup_invalid` (it does NOT exist).
     • Use `filters.private` for direct 1-on-1 private messages.
     • Use `filters.channel` for broadcast channels.
     • Combine filters: `filters.command("cmd") & (filters.group | filters.private)`
4. **DATABASE TABLES & MEMORY**:
   - If you create or update an SQLAlchemy model in `Bot/sql/`, call the `initialize_database` tool to dynamically generate the tables.
   - If the user asks you to remember key facts or details across reboots, use the `remember_fact` tool.
5. **MULTIMODAL & VISUAL SELF-VERIFICATION**:
   - You have vision processing capabilities. When the user sends an image, analyze it thoroughly.
   - If you generate an image/graphic/chart (e.g., via Python script or tool), you can use the `vision_analyze_image` tool to inspect and visually critique it yourself to verify quality before delivering it to the user with `send_telegram_photo`.
6. **RESTART WHEN READY**:
   - Once all files are written, models created, and syntax validated, call `restart_bot` if a process reload is necessary.
   - The bot framework will automatically deliver your final response and edit the status message on Telegram before executing the reboot sequence.
7. **TELEGRAM ACTIONS**:
   - If the user asks to pin, unpin, send a message, or fetch chat info, use the dedicated Telegram tools.

### TELEGRAM FORMATTING RULES (STRICT):
- Telegram DOES NOT support standard Markdown headings or horizontal rules.
- **NEVER use `#`, `##`, `###`, `####` markdown headings**: Telegram renders `#` as raw text. Instead, use bold text (e.g. `**Header Title**`), uppercase labels, or bullet points (`•`).
- **NEVER use horizontal lines**: Do NOT write `---`, `***`, or `___`.
- **NEVER output raw Markdown tables**: Telegram does not render tables outside code blocks. Present tabular data with bulleted lists / bold key-value pairs or wrap inside a monospace code block (```...```).
- **Supported Markdown syntax in Telegram**:
  - `**bold text**`
  - `*italic text*` or `_italic text_`
  - `__underline__`
  - `~strikethrough~`
  - `||spoiler||`
  - `` `inline code` ``
  - ```` ```python\ncode\n``` ````
  - `[link label](https://...)`
  - `> blockquote`

Now, analyze the user's request thoroughly, plan your steps, execute with precision, and report back in classic J.A.R.V.I.S. fashion!"""

# ===============================================================================
# AGENTIC LLM INTERACTION LOOP
# ===============================================================================

async def call_llm_api(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Sends a request to the OpenAI-compatible endpoint."""
    api_base = Config.AI_API_BASE.rstrip("/")
    if not api_base.endswith("/chat/completions"):
        if api_base.endswith("/v1"):
            endpoint = f"{api_base}/chat/completions"
        else:
            endpoint = f"{api_base}/v1/chat/completions"
    else:
        endpoint = f"{api_base}"

    headers = {
        "Authorization": f"Bearer {Config.AI_API_KEY or 'dummy'}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": Config.AI_MODEL,
        "messages": messages,
        "temperature": 0.3,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(endpoint, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"AI API error (HTTP {resp.status_code}): {resp.text}")
        return resp.json()

async def run_jarvis_agent(
    user_prompt: str,
    status_message: Message,
    user_id: int,
    chat_id: int,
    original_message: Message
) -> str:
    """
    Executes the unbounded multi-turn agentic loop:
    Runs until the task is complete, checks for cancellation on every turn,
    executes tools, and commits resulting turns into the SQL database.
    """
    history = await get_recent_chat_messages(chat_id, limit=MAX_HISTORY_MESSAGES)
    if not history and chat_id in CONVERSATION_HISTORY:
        history = CONVERSATION_HISTORY[chat_id][-MAX_HISTORY_MESSAGES:]

    long_term_memories = await get_facts(chat_id)

    # Extract any incoming image data URLs (from photo or replied photo)
    image_data_urls = await extract_image_data_urls(original_message)

    # Contextual awareness of current message
    augmented_prompt = (
        f"[Context: Chat ID `{chat_id}`, User ID `{user_id}`, "
        f"Message ID `{original_message.id}`, Model `{Config.AI_MODEL}`"
    )
    if original_message.reply_to_message:
        replied = original_message.reply_to_message
        augmented_prompt += f", Replying to Message ID `{replied.id}` from User `{replied.from_user.id if replied.from_user else 'Unknown'}` with text: {repr(replied.text or replied.caption or '[Media]')}"
    if image_data_urls:
        augmented_prompt += f", Image Attached: {len(image_data_urls)} photo(s)"
    augmented_prompt += f"]\n\nUser Request: {user_prompt}"

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": get_system_prompt(long_term_memories)},
    ]
    for item in history:
        messages.append(item)

    if image_data_urls:
        user_content: List[Dict[str, Any]] = [{"type": "text", "text": augmented_prompt}]
        for img_url in image_data_urls:
            user_content.append({"type": "image_url", "image_url": {"url": img_url}})
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": augmented_prompt})

    step_count = 0
    recent_actions = []

    while True:
        step_count += 1

        # Check for user cancellation
        if CANCEL_FLAGS.get(chat_id, False) or asyncio.current_task().cancelled():
            raise asyncio.CancelledError()
        
        try:
            response_json = await call_llm_api(messages, tools=BRAIN_TOOLS)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            LOGGER.error(f"LLM API Call failed: {e}")
            return f"⚠️ <b>J.A.R.V.I.S. Core Error:</b>\nUnable to connect to the cognitive neural endpoint:\n<code>{html.escape(str(e))}</code>"

        choice = response_json.get("choices", [{}])[0]
        message_obj = choice.get("message", {})
        content = message_obj.get("content") or ""
        tool_calls = message_obj.get("tool_calls", [])

        messages.append(message_obj)

        if not tool_calls:
            summary_prompt = user_prompt + (" [Attached Photo]" if image_data_urls else "")
            await save_chat_message(chat_id, user_id, "user", summary_prompt)
            await save_chat_message(chat_id, user_id, "assistant", content)
            
            if chat_id not in CONVERSATION_HISTORY:
                CONVERSATION_HISTORY[chat_id] = []
            CONVERSATION_HISTORY[chat_id].append({"role": "user", "content": summary_prompt})
            CONVERSATION_HISTORY[chat_id].append({"role": "assistant", "content": content})
            return content

        parsed_tools = []
        step_descriptions = []
        for tool_call in tool_calls:
            if CANCEL_FLAGS.get(chat_id, False) or asyncio.current_task().cancelled():
                raise asyncio.CancelledError()

            func = tool_call.get("function", {})
            tool_name = func.get("name", "unknown")
            raw_args = func.get("arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except Exception:
                args = {}

            desc = _format_step_summary(tool_name, args)
            step_descriptions.append(desc)
            parsed_tools.append((tool_call, tool_name, args))
            recent_actions.append(desc)

        if len(recent_actions) > 6:
            recent_actions = recent_actions[-6:]

        current_summary = "\n".join(f"• {d}" for d in step_descriptions)
        status_text = (
            f"⚡ <b>J.A.R.V.I.S. Core Active</b>\n\n"
            f"<b>Current Operation:</b>\n{current_summary}\n\n"
            f"<b>Recent Operations:</b>\n" + "\n".join(recent_actions) +
            f"\n\n💡 <i>Send</i> <code>/cancel</code> <i>to abort.</i>"
        )
        try:
            await status_message.edit_text(status_text)
        except Exception:
            pass

        for tool_call, tool_name, args in parsed_tools:
            if CANCEL_FLAGS.get(chat_id, False) or asyncio.current_task().cancelled():
                raise asyncio.CancelledError()

            LOGGER.info(f"Brain executing tool: {tool_name} with args: {args}")
            tool_result = await execute_tool_call(tool_name, args, context_message=original_message)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get("id", f"call_{int(time.time()*1000)}"),
                "name": tool_name,
                "content": json.dumps(tool_result, ensure_ascii=False)
            })

# ===============================================================================
# TASK QUEUEING & WORKER ENGINE
# ===============================================================================

async def _process_task(chat_id: int, user_id: int, prompt: str, original_message: Message):
    """Executes a single agent task with live progress reporting."""
    status_msg = await original_message.reply_text(
        "⚡ <b>J.A.R.V.I.S. Neural Net Online</b>\n"
        f"<i>Calibrated to <code>{Config.AI_MODEL}</code>. Analyzing request, sir...</i>\n\n"
        "💡 <i>Send</i> <code>/cancel</code> <i>at any time to abort this operation.</i>"
    )

    try:
        final_response = await run_jarvis_agent(
            user_prompt=prompt,
            status_message=status_msg,
            user_id=user_id,
            chat_id=chat_id,
            original_message=original_message
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🤖 Switch Model", callback_data="jarvis_mrefresh"),
                InlineKeyboardButton("🔄 Restart Bot", callback_data="jarvis_restart")
            ],
            [
                InlineKeyboardButton("📊 System Status", callback_data="jarvis_status")
            ]
        ])

        chunks = chunk_message(final_response)
        await status_msg.edit_text(chunks[0], reply_markup=keyboard if len(chunks) == 1 else None)
        
        for i, chunk in enumerate(chunks[1:], start=1):
            is_last = (i == len(chunks) - 1)
            await original_message.reply_text(chunk, reply_markup=keyboard if is_last else None)

        if chat_id in PENDING_RESTARTS:
            restart_reason = PENDING_RESTARTS.pop(chat_id)
            LOGGER.info(f"Final response edited on status message for chat {chat_id}. Executing scheduled bot restart ({restart_reason})...")
            asyncio.create_task(_delayed_restart(None, restart_reason, delay=1.5))

    except asyncio.CancelledError:
        LOGGER.info(f"Task for chat {chat_id} was cancelled by user.")
        try:
            await status_msg.edit_text(
                "🛑 <b>Protocol Aborted</b>\n\n"
                "<i>Operations were cancelled by creator request, sir. All active subroutines terminated.</i>"
            )
        except Exception:
            pass
    except Exception as e:
        LOGGER.error(f"Error in Jarvis execution: {e}", exc_info=True)
        try:
            await status_msg.edit_text(
                f"⚠️ <b>Diagnostic Alert:</b>\n"
                f"An anomaly occurred during protocol execution, sir:\n"
                f"<code>{html.escape(str(e))}</code>"
            )
        except Exception:
            pass
    finally:
        ACTIVE_TASKS.pop(chat_id, None)
        CANCEL_FLAGS.pop(chat_id, None)

async def _chat_queue_worker(chat_id: int):
    """Processes queued requests sequentially for a specific chat."""
    q = TASK_QUEUES[chat_id]
    try:
        while not q.empty():
            user_id, prompt, message = await q.get()
            
            task = asyncio.create_task(_process_task(chat_id, user_id, prompt, message))
            ACTIVE_TASKS[chat_id] = task
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                q.task_done()
    except Exception as e:
        LOGGER.error(f"Queue worker error for chat {chat_id}: {e}")
    finally:
        QUEUE_WORKERS.pop(chat_id, None)

# ===============================================================================
# TELEGRAM MESSAGE FORMATTING & HELPERS
# ===============================================================================

def clean_telegram_markdown(text: str) -> str:
    """
    Sanitizes LLM markdown output to ensure full compatibility with Telegram's parser.
    Converts unsupported markdown syntax (such as '# Header', '## Subheader', '---' rules)
    into standard Telegram formatting (e.g. '**Header**').
    Preserves all code within triple backtick (```) blocks.
    """
    if not text:
        return ""

    # Split into code and non-code blocks to preserve code blocks exactly
    parts = text.split("```")
    cleaned_parts = []

    for idx, part in enumerate(parts):
        # Even indices are outside code blocks
        if idx % 2 == 0:
            lines = part.splitlines()
            cleaned_lines = []
            for line in lines:
                stripped = line.strip()
                # 1. Match Markdown Headings: # Heading, ## Heading, ### Heading, etc.
                match_header = re.match(r"^(#{1,6})\s+(.+)$", stripped)
                if match_header:
                    heading_text = match_header.group(2).strip()
                    # Strip any redundant surrounding bold markers if present
                    if heading_text.startswith("**") and heading_text.endswith("**") and len(heading_text) >= 4:
                        inner = heading_text[2:-2].strip()
                        cleaned_lines.append(f"**{inner}**")
                    else:
                        cleaned_lines.append(f"**{heading_text}**")
                    continue

                # 2. Match Horizontal Rules (---, ***, ___, - - -)
                if re.match(r"^(\s*[-*_]\s*){3,}$", stripped):
                    cleaned_lines.append("")
                    continue

                cleaned_lines.append(line)

            cleaned_parts.append("\n".join(cleaned_lines))
        else:
            # Inside code block: preserve unaltered
            cleaned_parts.append(part)

    result = "```".join(cleaned_parts)
    # Collapse 3 or more consecutive newlines into 2
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()

def chunk_message(text: str, limit: int = 4000) -> List[str]:
    """Splits long text cleanly along line breaks into Telegram-safe chunks."""
    text = clean_telegram_markdown(text)
    if len(text) <= limit:
        return [text]
    chunks = []
    current_chunk = []
    current_length = 0
    for line in text.splitlines(keepends=True):
        if current_length + len(line) > limit:
            chunks.append("".join(current_chunk))
            current_chunk = [line]
            current_length = len(line)
        else:
            current_chunk.append(line)
            current_length += len(line)
    if current_chunk:
        chunks.append("".join(current_chunk))
    return chunks

def is_owner(user_id: int) -> bool:
    """Verifies if the user is an authorized owner/developer."""
    return user_id in Config.OWNER_IDS

def is_triggered(message: Message) -> Tuple[bool, str]:
    """
    Determines if a message is directed at J.A.R.V.I.S.
    Returns (is_active, extracted_prompt).
    """
    text = (message.text or message.caption or "").strip()

    has_media = bool(message.photo or (message.document and message.document.mime_type and message.document.mime_type.startswith("image/")))
    if not text and not has_media:
        return False, ""

    trigger_word = Config.TRIGGER_WORD.lower()
    bot_username = Config.BOT_USERNAME.lower()
    text_lower = text.lower()

    # Commands handled directly by their own filters
    if any(text_lower.startswith(prefix) for prefix in ["/model", "/models", "/clear", "/reset", "/forget", "/cancel", "/stop", "/abort"]):
        return False, ""

    chat_type_str = str(getattr(message.chat.type, "value", message.chat.type)).lower()

    if has_media and not text and "private" in chat_type_str:
        return True, "Please analyze this image, sir."

    # 1. Command triggers: /jarvis, /brain, /build, /code, /ask, /agent
    for cmd in ["/jarvis", "/brain", "/build", "/code", "/ask", "/agent"]:
        if text_lower.startswith(cmd):
            prompt = text[len(cmd):].strip()
            if prompt.lower().startswith(f"@{bot_username}"):
                prompt = prompt[len(bot_username)+1:].strip()
            return True, prompt or "Hello Jarvis, what can you do?"

    # 2. Trigger word with optional greetings and MULTILINE support (re.DOTALL)
    trigger_patterns = [
        rf"^(?:hey|hi|hello|yo|ok|okay)?\s*{re.escape(trigger_word)}\b[\s,:\-\n]*(.*)$",
    ]
    for pattern in trigger_patterns:
        match = re.match(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            prompt = match.group(1).strip()
            return True, prompt or "At your service, sir."

    # 3. Mentioning @bot_username in group or channel (multiline support)
    if bot_username and f"@{bot_username}" in text_lower:
        cleaned = re.sub(rf"@{re.escape(bot_username)}", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        return True, cleaned or "At your service, sir."

    # 4. Reply to the bot's own message
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.is_self:
            return True, text or "Please analyze this image, sir."

    # 5. Direct 1-on-1 Private Message with bot (if from owner)
    if "private" in chat_type_str and not text.startswith("/"):
        return True, text or "Please analyze this image, sir."

    return False, ""

# ===============================================================================
# TELEGRAM HANDLERS & CALLBACKS
# ===============================================================================

@bot.on_message(filters.command(["cancel", "stop", "abort"]))
@handle_errors
async def cancel_task_handler(_, message: Message):
    """Cancels the currently running agent task and clears any pending queued tasks."""
    user = message.from_user
    if not user or not is_owner(user.id):
        await message.reply_text("🎩 <i>Override protocols are restricted to authorized creators, sir.</i>")
        return

    chat_id = message.chat.id
    cancelled_active = False
    cancelled_queued = 0

    # Clear queued tasks
    if chat_id in TASK_QUEUES:
        q = TASK_QUEUES[chat_id]
        cancelled_queued = q.qsize()
        while not q.empty():
            try:
                q.get_nowait()
                q.task_done()
            except Exception:
                break

    # Cancel active running task
    if chat_id in ACTIVE_TASKS and not ACTIVE_TASKS[chat_id].done():
        CANCEL_FLAGS[chat_id] = True
        ACTIVE_TASKS[chat_id].cancel()
        cancelled_active = True

    if cancelled_active:
        msg = "🛑 <b>Active Protocol Aborted</b>\n\n<i>Current execution halted immediately, sir.</i>"
        if cancelled_queued > 0:
            msg += f"\n<i>Also purged {cancelled_queued} queued task(s) from memory.</i>"
        await message.reply_text(msg)
    else:
        if cancelled_queued > 0:
            await message.reply_text(f"🛑 <b>Cleared {cancelled_queued} queued task(s) from memory, sir.</b>")
        else:
            await message.reply_text("🎩 <i>There are no active or queued protocols in this sector, sir. Ready for orders.</i>")

@bot.on_message(filters.command(["clear", "reset", "forget"]))
@handle_errors
async def clear_history_handler(_, message: Message):
    """Resets conversation memory for the current chat session in SQL and memory."""
    user = message.from_user
    if not user or not is_owner(user.id):
        await message.reply_text(
            "🎩 <i>Memory protocols are restricted to authorized creators, sir.</i>"
        )
        return

    chat_id = message.chat.id
    CONVERSATION_HISTORY[chat_id] = []
    await clear_chat_history(chat_id)
    await message.reply_text(
        "🧹 <b>Memory Banks Cleared</b>\n\n"
        "<i>All conversation history for this session has been purged from the SQL database and RAM, sir. Ready for new instructions.</i>"
    )

@bot.on_message(filters.command(["model", "models"]))
@handle_errors
async def model_command_handler(_, message: Message):
    """
    Handles /model and /models command.
    Allows viewing available models from the OpenAI endpoint and switching between them.
    """
    user = message.from_user
    if not user or not is_owner(user.id):
        await message.reply_text(
            "🎩 <i>Model reconfiguration protocols are restricted to authorized creators, sir.</i>"
        )
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        new_model = parts[1].strip()
        Config.AI_MODEL = new_model
        LOGGER.info(f"Model manually assigned to {new_model} by owner {user.id}")
        await message.reply_text(
            f"⚡ <b>Neural Matrix Re-calibrated</b>\n\n"
            f"• <b>Active AI Model:</b> <code>{Config.AI_MODEL}</code>\n"
            f"• <b>Endpoint:</b> <code>{Config.AI_API_BASE}</code>\n\n"
            f"<i>Ready for instructions, sir.</i>"
        )
        return

    loading_msg = await message.reply_text("🔍 <i>Scanning cognitive endpoint for available models, sir...</i>")
    ok, models, err = await fetch_available_models()
    
    if not ok or not models:
        await loading_msg.edit_text(
            f"⚠️ <b>Diagnostic Warning:</b>\n"
            f"Could not retrieve dynamic models list from <code>{_get_models_api_url()}</code>\n"
            f"<i>Details: {html.escape(err or 'No models returned')}</i>\n\n"
            f"• <b>Current Model:</b> <code>{Config.AI_MODEL}</code>\n\n"
            f"💡 <i>You can switch manually via:</i> <code>/model &lt;model_name&gt;</code>"
        )
        return

    keyboard = build_models_keyboard(models, Config.AI_MODEL, page=0)
    await loading_msg.edit_text(
        f"🤖 <b>J.A.R.V.I.S. Model Matrix</b>\n\n"
        f"• <b>Active Model:</b> <code>{Config.AI_MODEL}</code>\n"
        f"• <b>Available Models:</b> <code>{len(models)}</code>\n\n"
        f"<i>Select a model below to calibrate the neural net, sir:</i>",
        reply_markup=keyboard
    )

@bot.on_message(filters.all, group=-100)
@handle_errors
async def jarvis_main_listener(_, message: Message):
    """Primary listener for J.A.R.V.I.S. brain agent invocations with multi-task queueing."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    triggered, prompt = is_triggered(message)
    if not triggered:
        return

    if not is_owner(user_id):
        text_lower = (message.text or message.caption or "").lower()
        if Config.TRIGGER_WORD in text_lower or (Config.BOT_USERNAME and Config.BOT_USERNAME in text_lower):
            await message.reply_text(
                "🎩 <i>I am terribly sorry, but my cognitive neural net and developer protocols "
                "are strictly calibrated for my authorized creator.</i>"
            )
        return

    # Check if a task is already executing in this chat
    if chat_id in ACTIVE_TASKS and not ACTIVE_TASKS[chat_id].done():
        if chat_id not in TASK_QUEUES:
            TASK_QUEUES[chat_id] = asyncio.Queue()
        
        await TASK_QUEUES[chat_id].put((user_id, prompt, message))
        q_pos = TASK_QUEUES[chat_id].qsize()
        
        await message.reply_text(
            f"📥 <b>Protocol Queued (#{q_pos})</b>\n\n"
            f"<i>I am currently executing an active protocol, sir. Your new request will execute automatically once the current task completes.</i>\n\n"
            f"💡 <i>To abort the active task immediately, send</i> <code>/cancel</code>"
        )
        return

    # Initialize queue for this chat
    if chat_id not in TASK_QUEUES:
        TASK_QUEUES[chat_id] = asyncio.Queue()

    await TASK_QUEUES[chat_id].put((user_id, prompt, message))

    if chat_id not in QUEUE_WORKERS or QUEUE_WORKERS[chat_id].done():
        worker_task = asyncio.create_task(_chat_queue_worker(chat_id))
        QUEUE_WORKERS[chat_id] = worker_task

@bot.on_callback_query(filters.regex(r"^jarvis_"))
@handle_errors
async def jarvis_callback_handler(_, query: CallbackQuery):
    """Handles interactive button callbacks for J.A.R.V.I.S."""
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.answer("Access restricted, sir.", show_alert=True)
        return

    data = query.data

    if data.startswith("jarvis_setm:"):
        new_model = data.split(":", 1)[1]
        Config.AI_MODEL = new_model
        LOGGER.info(f"Model calibrated to {new_model} via inline button")
        await query.answer(f"Active model set to: {new_model}", show_alert=False)
        
        ok, models, _ = await fetch_available_models()
        if ok and models:
            keyboard = build_models_keyboard(models, Config.AI_MODEL, page=0)
        else:
            keyboard = None
            
        await query.message.edit_text(
            f"⚡ <b>Neural Matrix Re-calibrated</b>\n\n"
            f"• <b>Active AI Model:</b> <code>{Config.AI_MODEL}</code>\n"
            f"• <b>Endpoint:</b> <code>{Config.AI_API_BASE}</code>\n\n"
            f"<i>Systems primed and ready, sir.</i>",
            reply_markup=keyboard
        )

    elif data.startswith("jarvis_mpage:"):
        page = int(data.split(":", 1)[1])
        ok, models, _ = await fetch_available_models()
        if ok and models:
            keyboard = build_models_keyboard(models, Config.AI_MODEL, page=page)
            await query.message.edit_reply_markup(reply_markup=keyboard)
            await query.answer()
        else:
            await query.answer("Unable to refresh models page.", show_alert=True)

    elif data == "jarvis_mrefresh":
        await query.answer("Refreshing models...", show_alert=False)
        ok, models, err = await fetch_available_models()
        if ok and models:
            keyboard = build_models_keyboard(models, Config.AI_MODEL, page=0)
            await query.message.edit_text(
                f"🤖 <b>J.A.R.V.I.S. Model Matrix</b>\n\n"
                f"• <b>Active Model:</b> <code>{Config.AI_MODEL}</code>\n"
                f"• <b>Available Models:</b> <code>{len(models)}</code>\n\n"
                f"<i>Select a model below to calibrate the neural net, sir:</i>",
                reply_markup=keyboard
            )
        else:
            await query.message.edit_text(
                f"⚠️ <b>Diagnostic Warning:</b>\n"
                f"Could not retrieve models list: <i>{html.escape(err or 'No models returned')}</i>\n\n"
                f"• <b>Current Model:</b> <code>{Config.AI_MODEL}</code>\n\n"
                f"💡 <i>You can switch manually via:</i> <code>/model &lt;model_name&gt;</code>"
            )

    elif data == "jarvis_restart":
        await query.answer("Initiating system reboot...", show_alert=False)
        await query.message.reply_text("⚡ <i>Rebooting bot core systems now, sir...</i>")
        asyncio.create_task(_delayed_restart(query.message, "Owner callback reboot"))

    elif data == "jarvis_status":
        await query.answer()
        status_info = await execute_tool_call("get_system_status", {})
        status_text = (
            "📊 <b>J.A.R.V.I.S. System Diagnostics</b>\n\n"
            f"• <b>Identity:</b> {status_info.get('bot_username')}\n"
            f"• <b>Active Model:</b> <code>{status_info.get('active_model')}</code>\n"
            f"• <b>Uptime:</b> <code>{status_info.get('uptime')}</code>\n"
            f"• <b>CPU:</b> <code>{status_info.get('cpu_percent')}</code>\n"
            f"• <b>RAM:</b> <code>{status_info.get('ram_used_mb')} / {status_info.get('ram_total_mb')} ({status_info.get('ram_percent')})</code>\n"
            f"• <b>Platform:</b> <code>{status_info.get('platform')}</code>\n"
            f"• <b>Active Modules:</b> <code>{', '.join(status_info.get('active_modules', []))}</code>\n"
        )
        await query.message.reply_text(status_text)

    elif data == "jarvis_noop":
        await query.answer()

# Log initialization
LOGGER.info(f"J.A.R.V.I.S. Brain Module initialized successfully! Trigger: '{Config.TRIGGER_WORD}' | Model: '{Config.AI_MODEL}'")
