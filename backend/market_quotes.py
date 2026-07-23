"""Validation for executable order-book ask prices."""


def has_valid_pm_asks(prices):
    return all(0 < float(prices.get(side, 0) or 0) <= 1 for side in ("Up", "Down"))


def is_fast_market_rejection(error):
    """Quote movement and vanished depth are normal misses, not system failures."""
    text = str(error or "")
    return any(marker in text for marker in (
        "真实盘口深度不足", "卖一深度不足", "报价变化后利润不足",
        "盘口无卖单", "可盈利深度不足",
    ))
