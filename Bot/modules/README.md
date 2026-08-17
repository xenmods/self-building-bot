# Bot Modules

This directory contains the command modules for the Telegram bot. Each module implements one or more related commands and is automatically loaded at bot startup.

## Structure

Modules are Python files that contain Pyrogram command handlers. The structure of a typical module is as follows:

```python
from Bot import bot
from Bot.core.decorators.tracking import track_user
from Bot.core.decorators.error_handler import handle_errors

from pyrogram import filters
from pyrogram.types import Message

@bot.on_message(filters.command("command_name"))
@track_user
@handle_errors
async def command_name(_, message: Message):
    # Command implementation
    await message.reply_text("Response")
```

## Creating New Modules

To create a new module:

1. Create a new Python file in the `Bot/modules/` directory (e.g., `my_commands.py`)
2. Import the necessary components:
   ```python
   from Bot import bot
   from pyrogram import filters
   from pyrogram.types import Message
   ```
3. Define your command handlers using Pyrogram decorators:
   ```python
   @bot.on_message(filters.command("mycommand"))
   async def my_command(_, message: Message):
       await message.reply_text("This is my command!")
   ```
4. Use the utility decorators as needed:
   ```python
   @bot.on_message(filters.command("mycommand"))
   @track_user  # Track user activity
   @handle_errors  # Handle errors gracefully
   async def my_command(_, message: Message):
       await message.reply_text("This is my command!")
   ```

The module will be automatically loaded at startup through the `__init__.py` file in this directory.

## Available Decorators

Use these decorators to add common functionality to your commands:

- `track_user` - Track user activity by updating their last seen time
- `handle_errors` - Catch and log errors, sending an error message to the user
- `rate_limit` - Limit how often a user can use a command

Example with rate limiting:

```python
from Bot.core.decorators.rate_limit import rate_limit

@bot.on_message(filters.command("limited"))
@track_user
@rate_limit(limit=1, window=60)  # Allow 1 use per 60 seconds
@handle_errors
async def limited_command(_, message: Message):
    await message.reply_text("This command is rate limited!")
```

## Using Inline Keyboards

You can create interactive messages with inline keyboards:

```python
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@bot.on_message(filters.command("buttons"))
async def buttons_command(_, message: Message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Button 1", callback_data="button1")],
        [InlineKeyboardButton("Button 2", callback_data="button2")]
    ])
    
    await message.reply_text("Here are some buttons:", reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^button"))
async def button_callback(_, callback_query):
    await callback_query.answer()
    await callback_query.message.reply_text(f"You pressed {callback_query.data}")
```

## Existing Modules

- `start.py` - Implements the basic commands:
  - `/start` - Initial greeting and bot information
  - `/help` - Help information and command list  
  - `/info` - User information display
  - `/stats` - Bot statistics

## Best Practices

1. Use decorators to ensure consistent behavior across commands
2. Group related commands in the same module
3. Keep command implementations concise and focused
4. Use meaningful command and function names
5. Add docstrings to explain what each command does
6. Handle different user inputs gracefully
7. Provide helpful error messages when something goes wrong 