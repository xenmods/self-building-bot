from typing import Optional

def format_user_mention(user_id: int, username: Optional[str] = None) -> str:
    """Format a user mention for display in messages."""
    if username:
        return f"@{username}"
    return f"[User](tg://user?id={user_id})"

def format_time(seconds: int) -> str:
    """Format seconds into a human-readable time string."""
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
    
    return " ".join(parts) 