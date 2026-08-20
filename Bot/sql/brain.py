"""
===============================================================================
                       SQL DATABASE PERSISTENCE FOR BRAIN
===============================================================================
Provides persistent conversation history and long-term episodic memory storage
for J.A.R.V.I.S. across bot reboots and hot-reloads.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import BigInteger, Column, DateTime, Integer, UnicodeText, select, delete
from Bot.sql import BASE, get_session
from Bot import LOGGER

class BrainMessage(BASE):
    """Stores individual conversational message turns persistently."""
    __tablename__ = "brain_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, index=True, nullable=False)
    user_id = Column(BigInteger, index=True, nullable=False)
    role = Column(UnicodeText, nullable=False)  # 'user', 'assistant', 'system'
    content = Column(UnicodeText, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    def __init__(self, chat_id: int, user_id: int, role: str, content: str):
        self.chat_id = chat_id
        self.user_id = user_id
        self.role = role
        self.content = content
        self.timestamp = datetime.utcnow()

    def __repr__(self):
        return f"<BrainMessage {self.id} chat={self.chat_id} role={self.role}>"


class BrainMemory(BASE):
    """Stores key-value long-term memories, facts, preferences, and custom context."""
    __tablename__ = "brain_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, index=True, nullable=False)
    key = Column(UnicodeText, index=True, nullable=False)
    value = Column(UnicodeText, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    def __init__(self, chat_id: int, key: str, value: str):
        self.chat_id = chat_id
        self.key = key
        self.value = value
        self.timestamp = datetime.utcnow()

    def __repr__(self):
        return f"<BrainMemory {self.id} key={self.key}>"


# ===============================================================================
# ASYNC DATABASE OPERATIONS
# ===============================================================================

async def save_chat_message(chat_id: int, user_id: int, role: str, content: str) -> None:
    """Saves a message turn into persistent database storage."""
    try:
        async with await get_session() as session:
            msg = BrainMessage(chat_id=chat_id, user_id=user_id, role=role, content=content)
            session.add(msg)
            await session.commit()
    except Exception as e:
        LOGGER.error(f"Failed to save brain message to SQL: {e}")

async def get_recent_chat_messages(chat_id: int, limit: int = 20) -> List[Dict[str, str]]:
    """Retrieves the recent conversation history for a chat in chronological order."""
    try:
        async with await get_session() as session:
            stmt = (
                select(BrainMessage)
                .where(BrainMessage.chat_id == chat_id)
                .order_by(BrainMessage.id.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            messages = result.scalars().all()
            # Reverse to get chronological order [oldest ... newest]
            return [{"role": m.role, "content": m.content} for m in reversed(messages)]
    except Exception as e:
        LOGGER.error(f"Failed to retrieve chat messages from SQL: {e}")
        return []

async def clear_chat_history(chat_id: int) -> bool:
    """Deletes all persistent conversation history for a chat."""
    try:
        async with await get_session() as session:
            stmt = delete(BrainMessage).where(BrainMessage.chat_id == chat_id)
            await session.execute(stmt)
            await session.commit()
            return True
    except Exception as e:
        LOGGER.error(f"Failed to clear chat history in SQL: {e}")
        return False

async def save_fact(chat_id: int, key: str, value: str) -> bool:
    """Saves or updates a persistent long-term fact/memory."""
    try:
        async with await get_session() as session:
            stmt = select(BrainMemory).where(
                BrainMemory.chat_id == chat_id,
                BrainMemory.key == key
            )
            res = await session.execute(stmt)
            memory = res.scalars().first()
            if memory:
                memory.value = value
                memory.timestamp = datetime.utcnow()
            else:
                memory = BrainMemory(chat_id=chat_id, key=key, value=value)
                session.add(memory)
            await session.commit()
            return True
    except Exception as e:
        LOGGER.error(f"Failed to save long-term fact to SQL: {e}")
        return False

async def get_facts(chat_id: int) -> Dict[str, str]:
    """Retrieves all persistent long-term memories/facts for a chat."""
    try:
        async with await get_session() as session:
            stmt = select(BrainMemory).where(BrainMemory.chat_id == chat_id)
            res = await session.execute(stmt)
            memories = res.scalars().all()
            return {m.key: m.value for m in memories}
    except Exception as e:
        LOGGER.error(f"Failed to retrieve long-term facts from SQL: {e}")
        return {}

async def delete_fact(chat_id: int, key: str) -> bool:
    """Deletes a specific long-term fact from SQL."""
    try:
        async with await get_session() as session:
            stmt = delete(BrainMemory).where(
                BrainMemory.chat_id == chat_id,
                BrainMemory.key == key
            )
            await session.execute(stmt)
            await session.commit()
            return True
    except Exception as e:
        LOGGER.error(f"Failed to delete long-term fact from SQL: {e}")
        return False
