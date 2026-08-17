from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from Bot.mongo import client, db, users_collection

async def add_user(user_id: int, username: str, first_name: Optional[str] = None, last_name: Optional[str] = None) -> bool:
    """
    Add a new user or update an existing user.
    
    Args:
        user_id: Telegram user ID
        username: Telegram username
        first_name: User's first name
        last_name: User's last name
        
    Returns:
        bool: True if user was added, False if user was updated
    """
    now = datetime.utcnow()
    
    # Check if user exists
    existing_user = await users_collection.find_one({"user_id": user_id})
    
    if existing_user:
        # Update existing user
        await users_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "last_seen": now
                }
            }
        )
        return False
    else:
        # Add new user
        await users_collection.insert_one({
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "join_date": now,
            "last_seen": now
        })
        return True

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a user by their ID.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Optional[Dict[str, Any]]: User document or None if not found
    """
    return await users_collection.find_one({"user_id": user_id})

async def get_all_users() -> List[Dict[str, Any]]:
    """
    Get all users.
    
    Returns:
        List[Dict[str, Any]]: List of all user documents
    """
    cursor = users_collection.find()
    return await cursor.to_list(length=None)

async def update_last_seen(user_id: int) -> bool:
    """
    Update a user's last seen time.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        bool: True if user was updated, False if user not found
    """
    result = await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"last_seen": datetime.utcnow()}}
    )
    return result.modified_count > 0

async def id_to_username(user_id: int) -> Optional[str]:
    """
    Get a username for a given user ID.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Optional[str]: Username or None if not found
    """
    user = await users_collection.find_one({"user_id": user_id}, {"username": 1})
    return user["username"] if user else None

async def get_user_count() -> int:
    """
    Get the total number of users.
    
    Returns:
        int: Total number of users
    """
    return await users_collection.count_documents({})

async def get_active_users(days: int = 7) -> int:
    """
    Get the number of active users in the last N days.
    
    Args:
        days: Number of days to consider for active users
        
    Returns:
        int: Number of active users
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    return await users_collection.count_documents({"last_seen": {"$gte": cutoff_date}})

async def get_user_stats() -> Dict[str, Any]:
    """
    Get user statistics.
    
    Returns:
        Dict[str, Any]: User statistics
    """
    total_users = await get_user_count()
    active_users = await get_active_users()
    
    return {
        "total_users": total_users,
        "active_users": active_users
    }

# Create indexes
async def create_indexes():
    """Create indexes for the users collection"""
    await users_collection.create_index("user_id", unique=True)
    await users_collection.create_index("last_seen")
