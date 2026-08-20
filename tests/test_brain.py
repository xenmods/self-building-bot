"""
Unit & Integration Tests for J.A.R.V.I.S. Self-Building Bot
"""

import asyncio
import os
import pathlib
import sys
from unittest.mock import AsyncMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pyrogram.types import Message, Chat, User

from Bot.config import Config
from Bot.sql import initialize_database
from Bot.sql.brain import (
    save_chat_message,
    get_recent_chat_messages,
    clear_chat_history,
    save_fact,
    get_facts,
    delete_fact
)
from Bot.modules.brain import (
    validate_python_code,
    search_duckduckgo,
    execute_tool_call,
    BRAIN_TOOLS,
    run_jarvis_agent,
    chunk_message,
    is_triggered,
    build_models_keyboard,
    fetch_available_models
)

async def test_all():
    print("=== Running J.A.R.V.I.S. Test Suite ===")
    
    # 0. Initialize SQL database tables
    await initialize_database()
    print("[OK] SQLAlchemy database initialized with Brain models.")

    # 1. Tools check
    assert len(BRAIN_TOOLS) >= 20, f"Expected at least 20 tools, got {len(BRAIN_TOOLS)}"
    print(f"[OK] {len(BRAIN_TOOLS)} tools verified.")

    # 2. Syntax validation
    valid, _ = validate_python_code("def add(a, b): return a + b")
    invalid, _ = validate_python_code("def add(a, b return a + b")
    assert valid and not invalid, "Syntax validation check failed"
    print("[OK] AST Syntax Validation operational.")

    # 2.5 Multiline Triggering Test
    fake_group_chat = Chat(id=-1001234567890, type="supergroup")
    fake_user = User(id=12345, first_name="Owner", is_self=False)
    multiline_prompt = """jarvis build an afk system where everyone can use /afk <text> or reply to a message (can be with media/file etc)

then if someone tags/mentions them u respond with their text or message if replied.

make it persistent in db"""
    test_msg = Message(id=99, chat=fake_group_chat, from_user=fake_user, text=multiline_prompt)
    trig, extracted = is_triggered(test_msg)
    assert trig, "Failed to trigger on multiline prompt!"
    assert "build an afk system" in extracted and "make it persistent in db" in extracted
    print("[OK] Multiline prompt triggering verified.")

    # 3. Test Persistent SQL Brain Memory
    test_chat_id = 777888999
    await clear_chat_history(test_chat_id)

    await save_chat_message(test_chat_id, 12345, "user", "jarvis remember we added cats")
    await save_chat_message(test_chat_id, 12345, "assistant", "Acknowledged, sir. Added cats.")
    
    history = await get_recent_chat_messages(test_chat_id, limit=10)
    assert len(history) == 2, f"Expected 2 messages, got {len(history)}"
    assert history[0]["content"] == "jarvis remember we added cats"
    print("[OK] Persistent SQL Message History verified across sessions.")

    # Test Facts Memory
    await save_fact(test_chat_id, "favorite_animal", "cats")
    facts = await get_facts(test_chat_id)
    assert facts.get("favorite_animal") == "cats"
    print("[OK] Persistent Long-term Facts verified in SQL.")

    # 4. Model keyboard & tools test
    mock_models = ["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet", "gemini-1.5-pro"]
    kb = build_models_keyboard(mock_models, "gpt-4o", page=0)
    assert kb and len(kb.inline_keyboard) > 0
    print("[OK] Dynamic Model Keyboard built successfully.")

    # Test switch_model tool
    switch_res = await execute_tool_call("switch_model", {"model_name": "claude-3-5-sonnet"})
    assert switch_res.get("success") is True and Config.AI_MODEL == "claude-3-5-sonnet"
    print("[OK] Model Switching Tool operational.")

    # 5. Tool execution test
    dir_res = await execute_tool_call("list_files", {"directory": "Bot"})
    assert "entries" in dir_res, "list_files failed"
    print("[OK] File tools operational.")

    # 6. Agent loop simulation
    fake_user = User(id=123456789, first_name="Owner", is_self=False)
    fake_chat = Chat(id=test_chat_id, type="private")
    fake_msg = Message(id=1, chat=fake_chat, from_user=fake_user, text="jarvis check system")
    fake_status = AsyncMock()
    fake_status.edit_text = AsyncMock()

    mock_resp = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "All systems nominal, sir.",
                    "tool_calls": None
                }
            }
        ]
    }
    with patch("Bot.modules.brain.call_llm_api", return_value=mock_resp):
        res = await run_jarvis_agent("check system", fake_status, 123456789, test_chat_id, fake_msg)
        assert "All systems nominal" in res
    print("[OK] Agent loop verified.")
    print("=== All Tests Succeeded! ===")

if __name__ == "__main__":
    asyncio.run(test_all())
