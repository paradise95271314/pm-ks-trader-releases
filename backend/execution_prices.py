"""Normalize actual exchange fill prices for position cost display."""

from decimal import Decimal, InvalidOperation


def kalshi_outcome_fill_price(order, outcome_side, fallback=0.0):
    try:
        yes_book_price = Decimal(str(order.get("average_fill_price", 0) or 0))
    except (InvalidOperation, TypeError, ValueError):
        return float(fallback or 0)
    if not Decimal("0") < yes_book_price < Decimal("1"):
        return float(fallback or 0)
    if str(outcome_side).strip().lower() == "no":
        return float(Decimal("1") - yes_book_price)
    return float(yes_book_price)


def polymarket_fill_price(response, fallback=0.0):
    try:
        paid = float(response.get("makingAmount", 0) or 0)
        shares = float(response.get("takingAmount", 0) or 0)
    except (TypeError, ValueError):
        return float(fallback or 0)
    price = paid / shares if shares > 0 else 0
    return price if 0 < price < 1 else float(fallback or 0)


def result_fill_price(result, platform):
    plan_key, result_key = ("pm_plan", "pm") if platform == "pm" else ("ks_plan", "ks")
    fill = (result.get(result_key) or {}).get("avg_outcome_price")
    fallback = (result.get(plan_key) or {}).get("price", 0)
    try:
        return float(fill) if fill is not None else float(fallback or 0)
    except (TypeError, ValueError):
        return float(fallback or 0)
