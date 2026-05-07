# from slowapi import Limiter
# from slowapi.util import get_remote_address

# limiter = Limiter(key_func=get_remote_address)

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

from app.core.security import decode_access_token


def get_rate_limit_key(request: Request) -> str:
    """
    Rate limit key strategy:
    - Authenticated users  → keyed by user email (per-user limit)
    - Anonymous users      → keyed by IP address (per-IP limit)

    Why: two authenticated users sharing office WiFi should not
    share a rate limit quota. Per-user is fairer and more precise.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            return f"user:{payload['sub']}"

    # Fall back to IP for anonymous requests
    return get_remote_address(request)


limiter = Limiter(key_func=get_rate_limit_key)
