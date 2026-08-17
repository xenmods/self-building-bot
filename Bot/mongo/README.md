# MongoDB Module

This directory contains the MongoDB models and operations for the Telegram bot. The bot uses Motor AsyncIO to interact with MongoDB asynchronously.

## Structure

The MongoDB module consists of:

- `__init__.py` - Sets up the MongoDB connection with Motor AsyncIO
- `users.py` - Implements the User model and user-related operations

## MongoDB Connection

The MongoDB connection is established in `__init__.py` using Motor's AsyncIOMotorClient. The connection string is read from the environment variables.

```python
from motor.motor_asyncio import AsyncIOMotorClient
from Bot.config import MONGO_URI

# Initialize MongoDB connection
client = AsyncIOMotorClient(MONGO_URI)
db = client.get_default_database()
users_collection = db.users
```

## User Model

The User model (`users.py`) stores information about bot users:

```python
{
    "user_id": 123456789,
    "username": "john_doe",
    "first_name": "John",
    "last_name": "Doe",
    "join_date": datetime.utcnow(),
    "last_seen": datetime.utcnow()
}
```

### Fields

- `user_id` - Telegram user ID (primary key)
- `username` - Telegram username
- `first_name` - User's first name
- `last_name` - User's last name
- `join_date` - When the user first interacted with the bot
- `last_seen` - When the user last interacted with the bot

## User Operations

The `users.py` file provides several async functions for user operations:

- `add_user(user_id, username, first_name, last_name)` - Add a new user or update existing user
- `get_user(user_id)` - Get a user by their ID
- `get_all_users()` - Get all users
- `update_last_seen(user_id)` - Update a user's last seen time
- `id_to_username(user_id)` - Get a username for a given user ID
- `get_user_count()` - Get the total number of users
- `get_active_users(days)` - Get the number of active users in the last N days
- `get_user_stats()` - Get user statistics
- `create_indexes()` - Create indexes for the users collection

## Example Usage

### Adding or Updating a User

```python
from Bot.mongo.users import add_user

# Add a new user or update existing user
was_added = await add_user(
    user_id=123456789,
    username="john_doe",
    first_name="John",
    last_name="Doe"
)
if was_added:
    print("New user added")
else:
    print("Existing user updated")
```

### Getting User Information

```python
from Bot.mongo.users import get_user

# Get user information
user = await get_user(123456789)
if user:
    print(f"Username: {user['username']}")
    print(f"First name: {user['first_name']}")
    print(f"Last seen: {user['last_seen']}")
```

### Updating Last Seen

```python
from Bot.mongo.users import update_last_seen

# Update user's last seen time
updated = await update_last_seen(123456789)
```

### Getting User Statistics

```python
from Bot.mongo.users import get_user_stats

# Get user statistics
stats = await get_user_stats()
print(f"Total users: {stats['total_users']}")
print(f"Active users: {stats['active_users']}")
```

## Creating New Models

To create a new MongoDB model:

1. Create a new Python file in the `Bot/mongo/` directory (e.g., `messages.py`)
2. Import the necessary components:
   ```python
   from datetime import datetime
   from typing import Optional, List, Dict, Any
   from motor.motor_asyncio import AsyncIOMotorCollection
   
   from Bot.mongo import client, db
   ```
3. Define your collection:
   ```python
   # Get collection reference
   messages_collection = db.messages
   ```
4. Implement async operations:
   ```python
   async def add_message(user_id: int, text: str) -> str:
       """
       Add a new message.
       
       Args:
           user_id: Telegram user ID
           text: Message text
           
       Returns:
           str: Message ID
       """
       result = await messages_collection.insert_one({
           "user_id": user_id,
           "text": text,
           "timestamp": datetime.utcnow()
       })
       return str(result.inserted_id)
   ```

5. Create indexes in an async function:
   ```python
   async def create_indexes():
       """Create indexes for the messages collection"""
       await messages_collection.create_index("user_id")
       await messages_collection.create_index("timestamp")
   ```

## Best Practices

1. Use appropriate indexes for frequently queried fields:
   ```python
   # Create indexes
   async def create_indexes():
       await users_collection.create_index("user_id", unique=True)
       await users_collection.create_index("last_seen")
   ```

2. Use projection to limit the fields returned:
   ```python
   # Only get the username field
   user = await users_collection.find_one({"user_id": user_id}, {"username": 1})
   ```

3. Use bulk operations for multiple updates:
   ```python
   # Update multiple users at once
   operations = [
       UpdateOne({"user_id": user_id}, {"$set": {"last_seen": now}})
       for user_id in user_ids
   ]
   await users_collection.bulk_write(operations)
   ```

4. Handle MongoDB errors gracefully:
   ```python
   try:
       result = await users_collection.insert_one(user_data)
   except Exception as e:
       LOGGER.error(f"Failed to insert user: {e}")
       return False
   ```

5. Call create_indexes() during application startup:
   ```python
   # In your app startup code
   from Bot.mongo.users import create_indexes
   
   async def startup():
       # Create indexes for better query performance
       await create_indexes()
   ``` 