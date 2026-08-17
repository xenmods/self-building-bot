import time
from functools import wraps
from pyrogram.types import Message

def rate_limit(limit: int, window: int = 60):
    """
    Rate limit a function to a certain number of calls per time window.
    
    Args:
        limit: Maximum number of calls allowed in the time window
        window: Time window in seconds (default: 60)
    """
    def decorator(func):
        # Store the last call time for each user
        last_call = {}
        
        @wraps(func)
        async def wrapper(client, message, *args, **kwargs):
            user_id = message.from_user.id
            
            # Check if user is rate limited
            if user_id in last_call:
                elapsed = time.time() - last_call[user_id]
                if elapsed < window:
                    # User is rate limited
                    await message.reply_text(
                        f"Please wait {int(window - elapsed)} seconds before using this command again."
                    )
                    return
            
            # Update last call time
            last_call[user_id] = time.time()
            
            # Call the function
            return await func(client, message, *args, **kwargs)
        
        return wrapper
    
    return decorator 