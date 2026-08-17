from functools import wraps
from pyrogram.types import Message
from Bot import LOGGER

def handle_errors(func):
    """Decorator to handle errors in a function."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            LOGGER.error(f"Error in {func.__name__}: {e}", exc_info=True)
            # If the function has a message parameter, reply to it
            for arg in args:
                if isinstance(arg, Message):
                    await arg.reply_text(f"An error occurred: {str(e)}")
                    break
            return None
    
    return wrapper 