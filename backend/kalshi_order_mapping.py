"""Pure Kalshi V2 order-direction and price mapping helpers."""

from decimal import Decimal, InvalidOperation


def _price(market, field):
    try:
        value = Decimal(str(market.get(field, "0") or "0"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Kalshi {field}") from exc
    if not Decimal("0") < value < Decimal("1"):
        raise ValueError(f"Kalshi {field} must be between 0 and 1, got {value}")
    return value


def build_buy_quote(outcome_side, market):
    """Map a desired YES/NO position to Kalshi's YES-book V2 order shape."""
    outcome_side = str(outcome_side).strip().lower()
    if outcome_side == "yes":
        yes_ask = _price(market, "yes_ask_dollars")
        return {
            "outcome_side": "yes",
            "book_side": "bid",
            "book_price": yes_ask,
            "outcome_price": yes_ask,
        }
    if outcome_side == "no":
        yes_bid = _price(market, "yes_bid_dollars")
        no_ask = _price(market, "no_ask_dollars")
        if abs((Decimal("1") - yes_bid) - no_ask) > Decimal("0.011"):
            raise ValueError("Kalshi YES bid and NO ask are inconsistent")
        return {
            "outcome_side": "no",
            "book_side": "ask",
            "book_price": yes_bid,
            "outcome_price": no_ask,
        }
    raise ValueError(f"Invalid Kalshi outcome side: {outcome_side!r}")


def build_close_quote(outcome_side, market):
    """Map closing a YES/NO position to the opposite Kalshi book action."""
    outcome_side = str(outcome_side).strip().lower()
    if outcome_side == "yes":
        yes_bid = _price(market, "yes_bid_dollars")
        return {
            "outcome_side": "yes",
            "book_side": "ask",
            "book_price": yes_bid,
        }
    if outcome_side == "no":
        yes_ask = _price(market, "yes_ask_dollars")
        return {
            "outcome_side": "no",
            "book_side": "bid",
            "book_price": yes_ask,
        }
    raise ValueError(f"Invalid Kalshi outcome side: {outcome_side!r}")
