from typing import List

def parse_args(text: str) -> List[str]:
    """Parse command arguments from a message text."""
    if not text:
        return []
    
    # Split by whitespace but keep quoted strings together
    args = []
    current = ""
    in_quotes = False
    
    for char in text:
        if char == '"' and not in_quotes:
            in_quotes = True
        elif char == '"' and in_quotes:
            in_quotes = False
        elif char == ' ' and not in_quotes:
            if current:
                args.append(current)
                current = ""
        else:
            current += char
    
    if current:
        args.append(current)
    
    return args 