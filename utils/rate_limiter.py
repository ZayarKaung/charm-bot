"""Rate limiter for Charm Bot free tier."""

import logging

from models.user import is_within_limit

logger = logging.getLogger(__name__)


async def check_rate_limit(db, user_id: int, free_limit: int) -> tuple[bool, int]:
    """
    Check if the user is within their daily rate limit.

    Returns:
        (allowed, remaining): Whether the request is allowed, and how many remain.
    """
    await db.reset_usage_if_needed(user_id)
    user = await db.get_user(user_id)
    if user is None:
        return True, free_limit

    is_premium = bool(user["is_premium"])

    if is_premium:
        return True, -1  # -1 means unlimited

    daily_count = user["daily_count"]
    allowed = is_within_limit(daily_count, is_premium, free_limit)
    remaining = max(0, free_limit - daily_count)

    if not allowed:
        logger.info(
            "Rate limit exceeded for user %s (%d/%d)",
            user_id, daily_count, free_limit
        )

    return allowed, remaining
