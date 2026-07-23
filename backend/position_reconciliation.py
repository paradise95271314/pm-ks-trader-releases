"""Reconcile local trade metadata with live exchange positions."""


def polymarket_position_sizes(payload):
    rows = payload if isinstance(payload, list) else (payload or {}).get("positions", [])
    result = {}
    for row in rows or []:
        token_id = str(row.get("asset") or row.get("token_id") or "")
        try:
            size = float(row.get("size", 0) or 0)
        except (TypeError, ValueError):
            continue
        if token_id and size > 0.01:
            result[token_id] = result.get(token_id, 0.0) + size
    return result


def kalshi_position_sizes(payload):
    result = {}
    for row in (payload or {}).get("market_positions", []) or []:
        ticker = str(row.get("ticker") or row.get("market_ticker") or "")
        try:
            raw_position = row.get("position_fp")
            if raw_position in (None, ""):
                raw_position = row.get("position", 0)
            position = float(raw_position or 0)
        except (TypeError, ValueError):
            continue
        if ticker:
            result[(ticker, "yes")] = max(position, 0.0)
            result[(ticker, "no")] = max(-position, 0.0)
    return result


def reconcile_positions(history, pm_live=None, ks_live=None):
    """Allocate live totals across recent trades without changing history."""
    pm_left = dict(pm_live or {}) if pm_live is not None else None
    ks_left = dict(ks_live or {}) if ks_live is not None else None
    positions = []
    for trade in reversed(history):
        if not trade.get("success"):
            continue
        qty = float(trade.get("hedged_qty") or trade.get("pm_filled_qty") or trade.get("ks_fill_count") or 0)
        item = dict(trade)

        local_pm = max(0.0, qty - float(item.get("pm_closed_qty", 0) or 0))
        token_id = str(item.get("token_id") or "")
        if pm_left is None or not token_id:
            pm_remaining = local_pm
        else:
            pm_remaining = min(qty, max(0.0, pm_left.get(token_id, 0.0)))
            pm_left[token_id] = max(0.0, pm_left.get(token_id, 0.0) - pm_remaining)

        local_ks = max(0.0, qty - float(item.get("ks_closed_qty", 0) or 0))
        ticker = str(item.get("ks_ticker") or "")
        side = str(item.get("ks_side") or item.get("kalshi_leg") or "yes").lower()
        key = (ticker, side)
        if ks_left is None or not ticker:
            ks_remaining = local_ks
        else:
            ks_remaining = min(qty, max(0.0, ks_left.get(key, 0.0)))
            ks_left[key] = max(0.0, ks_left.get(key, 0.0) - ks_remaining)

        item["pm_remaining"] = round(pm_remaining, 4)
        item["ks_remaining"] = round(ks_remaining, 4)
        if item["pm_remaining"] > 0.01 or item["ks_remaining"] > 0.01:
            positions.append(item)
    positions.reverse()
    return positions
