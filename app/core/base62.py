"""
Base62 encoding for short code generation.

Strategy:
  - Insert URL row → get auto-incremented integer ID
  - Encode that ID to Base62 (a-zA-Z0-9)
  - Store result as short_code

Why Base62?
  - No collisions guaranteed (each ID is unique)
  - Predictable length growth (ID 1 → "1", ID 3.5B → 6 chars)
  - URL-safe characters only — no special chars needed
  - Decode back to ID in O(n) where n = code length

Examples:
  encode(1)   → "1"
  encode(62)  → "10"
  encode(125) → "cb"
"""

BASE62_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def encode(num: int) -> str:
    """Convert a positive integer ID to a Base62 short code."""
    if num <= 0:
        raise ValueError(f"ID must be a positive integer, got: {num}")

    result = []
    while num:
        result.append(BASE62_CHARS[num % 62])
        num //= 62

    return "".join(reversed(result))


def decode(code: str) -> int:
    """Convert a Base62 short code back to the original integer ID."""
    if not code:
        raise ValueError("Short code cannot be empty")

    result = 0
    for char in code:
        if char not in BASE62_CHARS:
            raise ValueError(f"Invalid Base62 character: '{char}'")
        result = result * 62 + BASE62_CHARS.index(char)

    return result
